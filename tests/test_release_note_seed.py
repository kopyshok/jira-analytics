"""Тесты сидера release_notes/*.json → БД."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.release_note import ReleaseNote
from app.services.release_note_seed import ReleaseNoteSeeder, seed_from_files


def _write(dir_: Path, version: str, notes: list[dict]) -> None:
    (dir_ / f"{version}.json").write_text(
        json.dumps({"version": version, "notes": notes}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_seed_creates_records(tmp_path: Path, db_session: Session):
    _write(tmp_path, "v1.0.0", [
        {"type": "new", "section": "general", "title": "T1", "description": "D1"},
        {"type": "fix", "section": "sync", "title": "T2", "description": "D2"},
    ])
    stats = seed_from_files(db_session, tmp_path)
    assert stats == {"created": 2, "updated": 0, "unchanged": 0, "files": 1}
    rows = db_session.query(ReleaseNote).order_by(ReleaseNote.title).all()
    assert [r.title for r in rows] == ["T1", "T2"]
    assert rows[0].version == "v1.0.0"


def test_seed_is_idempotent(tmp_path: Path, db_session: Session):
    _write(tmp_path, "v1.0.0", [
        {"type": "new", "section": "general", "title": "T1", "description": "D1"},
    ])
    seed_from_files(db_session, tmp_path)
    stats = seed_from_files(db_session, tmp_path)
    assert stats["created"] == 0
    assert stats["unchanged"] == 1
    assert db_session.query(ReleaseNote).count() == 1


def test_seed_updates_description_but_preserves_is_hidden(
    tmp_path: Path, db_session: Session,
):
    _write(tmp_path, "v1.0.0", [
        {"type": "new", "section": "general", "title": "T1", "description": "old"},
    ])
    seed_from_files(db_session, tmp_path)
    # Пользователь скрыл запись через админку
    note = db_session.query(ReleaseNote).one()
    note.is_hidden = True
    db_session.commit()

    # Разработчик исправил опечатку в файле
    _write(tmp_path, "v1.0.0", [
        {"type": "new", "section": "general", "title": "T1", "description": "new"},
    ])
    stats = seed_from_files(db_session, tmp_path)
    assert stats["updated"] == 1

    refreshed = db_session.query(ReleaseNote).one()
    assert refreshed.description == "new"
    assert refreshed.is_hidden is True  # не перетёрто


def test_seed_skips_bad_entries(tmp_path: Path, db_session: Session, caplog):
    _write(tmp_path, "v1.0.0", [
        {"type": "wat", "section": "general", "title": "Bad type", "description": "D"},
        {"type": "fix", "section": "alien", "title": "Bad section", "description": "D"},
        {"type": "fix", "section": "general", "title": "", "description": "D"},
        {"type": "fix", "section": "general", "title": "OK", "description": "D"},
    ])
    seed_from_files(db_session, tmp_path)
    titles = [n.title for n in db_session.query(ReleaseNote).all()]
    assert titles == ["OK"]


def test_seed_missing_directory_is_noop(tmp_path: Path, db_session: Session):
    stats = seed_from_files(db_session, tmp_path / "does-not-exist")
    assert stats == {"created": 0, "updated": 0, "unchanged": 0, "files": 0}


def test_seed_invalid_json_logs_and_continues(
    tmp_path: Path, db_session: Session,
):
    (tmp_path / "v1.0.0.json").write_text("not valid json {", encoding="utf-8")
    _write(tmp_path, "v1.0.1", [
        {"type": "fix", "section": "general", "title": "OK", "description": "D"},
    ])
    stats = seed_from_files(db_session, tmp_path)
    assert stats["files"] == 2
    assert stats["created"] == 1
