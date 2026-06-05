"""CLI для добавления записей в ленту «Что нового».

Источник правды — `release_notes/<version>.json` в репозитории. БД заполняется
сидером при старте приложения (`app.services.release_note_seed`).

Использование:
    py -3.10 scripts/release_note.py add --type fix --section sync \\
        --title "..." --description "..."
        # → добавит запись в release_notes/drafts.json

    py -3.10 scripts/release_note.py add --type new --section scenarios \\
        --title "..." --description "..." --version v1.1.0
        # → ретро: добавит запись сразу в release_notes/v1.1.0.json

    py -3.10 scripts/release_note.py bind --version v1.2.0
        # → перенесёт все записи из drafts.json в release_notes/v1.2.0.json
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_NOTES_DIR = _REPO_ROOT / "release_notes"
_DRAFTS_FILE = _NOTES_DIR / "drafts.json"

_NOTE_TYPES = ("new", "improvement", "fix")
_SECTIONS = (
    "scenarios", "resources", "analytics", "issues",
    "dashboard", "backlog", "sync", "settings", "general",
)


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _version_file(version: str) -> Path:
    return _NOTES_DIR / f"{version}.json"


def cmd_add(args) -> int:
    if args.type not in _NOTE_TYPES:
        sys.stderr.write(f"Ошибка: неизвестный тип записи: {args.type!r}\n")
        return 2
    if args.section not in _SECTIONS:
        sys.stderr.write(f"Ошибка: неизвестный раздел: {args.section!r}\n")
        return 2

    note: dict = {
        "type": args.type,
        "section": args.section,
        "title": args.title.strip(),
        "description": args.description.strip(),
        "sort_order": 0,
    }
    if args.help_link:
        note["help_link"] = args.help_link

    if args.version:
        target = _version_file(args.version)
        payload = _load(target) or {"version": args.version, "notes": []}
        payload.setdefault("notes", []).append(note)
        _save(target, payload)
        sys.stdout.write(f"OK: добавлено в {target.relative_to(_REPO_ROOT)}\n")
    else:
        payload = _load(_DRAFTS_FILE) or {"notes": []}
        payload.setdefault("notes", []).append(note)
        _save(_DRAFTS_FILE, payload)
        sys.stdout.write(f"OK: черновик добавлен в {_DRAFTS_FILE.relative_to(_REPO_ROOT)}\n")
    return 0


def cmd_bind(args) -> int:
    version = args.version
    if not version.startswith("v"):
        version = "v" + version

    drafts = _load(_DRAFTS_FILE)
    pending = drafts.get("notes") if drafts else []
    if not pending:
        sys.stdout.write("Нет черновиков для привязки.\n")
        return 0

    target = _version_file(version)
    payload = _load(target) or {"version": version, "notes": []}
    payload["version"] = version
    payload.setdefault("notes", []).extend(pending)
    _save(target, payload)

    _DRAFTS_FILE.unlink(missing_ok=True)
    sys.stdout.write(
        f"Привязано {len(pending)} заметок → "
        f"{target.relative_to(_REPO_ROOT)}\n"
    )
    return 0


def _maybe_fix_win32_encoding() -> None:
    if sys.platform != "win32":
        return
    try:
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )
    except (AttributeError, ValueError):
        pass


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Release notes CLI (file-based)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Добавить запись (черновик или ретро)")
    p_add.add_argument("--type", required=True, choices=list(_NOTE_TYPES))
    p_add.add_argument("--section", required=True)
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--description", required=True)
    p_add.add_argument("--help-link", default=None)
    p_add.add_argument("--version", default=None, help="Сразу под версию (ретро)")
    p_add.set_defaults(func=cmd_add)

    p_bind = sub.add_parser("bind", help="Привязать черновики к версии")
    p_bind.add_argument("--version", required=True)
    p_bind.set_defaults(func=cmd_bind)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    _maybe_fix_win32_encoding()
    raise SystemExit(main())
