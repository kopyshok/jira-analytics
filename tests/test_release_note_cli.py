"""Тесты CLI-скрипта scripts/release_note.py."""
from sqlalchemy.orm import Session

from app.models.release_note import ReleaseNote
from scripts.release_note import main


def test_add_command_creates_draft(db_session: Session):
    rc = main([
        "add",
        "--type", "fix",
        "--section", "sync",
        "--title", "Test",
        "--description", "Desc",
    ], db=db_session)
    assert rc == 0
    notes = db_session.query(ReleaseNote).all()
    assert len(notes) == 1
    assert notes[0].note_type == "fix"
    assert notes[0].section == "sync"
    assert notes[0].version is None


def test_add_with_version_publishes_directly(db_session: Session):
    rc = main([
        "add",
        "--type", "new",
        "--section", "scenarios",
        "--title", "Retro entry",
        "--description", "Description",
        "--version", "v1.1.0",
    ], db=db_session)
    assert rc == 0
    note = db_session.query(ReleaseNote).first()
    assert note.version == "v1.1.0"


def test_bind_drafts_to_version(db_session: Session):
    main(["add", "--type", "fix", "--section", "sync",
          "--title", "X", "--description", "Y"], db=db_session)
    main(["add", "--type", "new", "--section", "general",
          "--title", "A", "--description", "B"], db=db_session)
    rc = main(["bind", "--version", "v1.2.0"], db=db_session)
    assert rc == 0
    notes = db_session.query(ReleaseNote).all()
    assert len(notes) == 2
    assert all(n.version == "v1.2.0" for n in notes)


def test_invalid_type_returns_nonzero(db_session: Session):
    # argparse choices=[...] завершает процесс кодом 2 через SystemExit —
    # внутри тестов это поднимет SystemExit.
    import pytest
    with pytest.raises(SystemExit):
        main([
            "add", "--type", "wat", "--section", "general",
            "--title", "X", "--description", "Y",
        ], db=db_session)


def test_bind_with_bad_version_format_returns_nonzero(db_session: Session):
    main(["add", "--type", "fix", "--section", "sync",
          "--title", "X", "--description", "Y"], db=db_session)
    rc = main(["bind", "--version", "v1.2.0-rc1"], db=db_session)
    assert rc == 2
