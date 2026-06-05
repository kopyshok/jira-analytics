"""Тесты CLI-скрипта scripts/release_note.py (file-based)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.release_note as cli


@pytest.fixture
def notes_dir(tmp_path, monkeypatch):
    """Изолированная директория release_notes для CLI."""
    monkeypatch.setattr(cli, "_NOTES_DIR", tmp_path)
    monkeypatch.setattr(cli, "_DRAFTS_FILE", tmp_path / "drafts.json")
    monkeypatch.setattr(cli, "_REPO_ROOT", tmp_path)
    return tmp_path


def test_add_command_creates_draft(notes_dir: Path):
    rc = cli.main([
        "add",
        "--type", "fix",
        "--section", "sync",
        "--title", "Test",
        "--description", "Desc",
    ])
    assert rc == 0
    drafts = json.loads((notes_dir / "drafts.json").read_text(encoding="utf-8"))
    assert len(drafts["notes"]) == 1
    assert drafts["notes"][0]["type"] == "fix"
    assert drafts["notes"][0]["section"] == "sync"
    assert drafts["notes"][0]["title"] == "Test"


def test_add_with_version_writes_directly(notes_dir: Path):
    rc = cli.main([
        "add",
        "--type", "new",
        "--section", "scenarios",
        "--title", "Retro entry",
        "--description", "Description",
        "--version", "v1.1.0",
    ])
    assert rc == 0
    payload = json.loads((notes_dir / "v1.1.0.json").read_text(encoding="utf-8"))
    assert payload["version"] == "v1.1.0"
    assert payload["notes"][0]["title"] == "Retro entry"
    assert not (notes_dir / "drafts.json").exists()


def test_bind_drafts_to_version(notes_dir: Path):
    cli.main(["add", "--type", "fix", "--section", "sync",
              "--title", "X", "--description", "Y"])
    cli.main(["add", "--type", "new", "--section", "general",
              "--title", "A", "--description", "B"])
    rc = cli.main(["bind", "--version", "v1.2.0"])
    assert rc == 0
    payload = json.loads((notes_dir / "v1.2.0.json").read_text(encoding="utf-8"))
    assert payload["version"] == "v1.2.0"
    assert len(payload["notes"]) == 2
    assert not (notes_dir / "drafts.json").exists()


def test_bind_appends_to_existing_version_file(notes_dir: Path):
    cli.main([
        "add", "--type", "new", "--section", "general",
        "--title", "Pre-existing", "--description", "D",
        "--version", "v1.2.0",
    ])
    cli.main(["add", "--type", "fix", "--section", "sync",
              "--title", "New draft", "--description", "D"])
    cli.main(["bind", "--version", "v1.2.0"])
    payload = json.loads((notes_dir / "v1.2.0.json").read_text(encoding="utf-8"))
    titles = [n["title"] for n in payload["notes"]]
    assert "Pre-existing" in titles
    assert "New draft" in titles


def test_invalid_type_exits(notes_dir: Path):
    with pytest.raises(SystemExit):
        cli.main([
            "add", "--type", "wat", "--section", "general",
            "--title", "X", "--description", "Y",
        ])


def test_bind_without_drafts_is_noop(notes_dir: Path):
    rc = cli.main(["bind", "--version", "v1.2.0"])
    assert rc == 0
    assert not (notes_dir / "v1.2.0.json").exists()
