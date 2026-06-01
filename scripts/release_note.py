"""CLI для добавления записей в ленту «Что нового».

Использование:
    py -3.10 scripts/release_note.py add --type fix --section sync \\
        --title "..." --description "..."
    py -3.10 scripts/release_note.py add --type new --section scenarios \\
        --title "..." --description "..." --version v1.1.0  # ретро
    py -3.10 scripts/release_note.py bind --version v1.2.0
"""
from __future__ import annotations

import argparse
import io
import sys
from typing import Optional

from sqlalchemy.orm import Session


def _get_db() -> Session:
    from app.database import SessionLocal
    return SessionLocal()


def cmd_add(args, db: Session) -> int:
    from app.services.release_note_service import ReleaseNoteService
    svc = ReleaseNoteService(db)
    try:
        note = svc.create_draft(
            note_type=args.type,
            section=args.section,
            title=args.title,
            description=args.description,
            help_link=args.help_link,
        )
    except ValueError as e:
        sys.stderr.write(f"Ошибка: {e}\n")
        return 2
    if args.version:
        note.version = args.version
        db.commit()
    sys.stdout.write(f"OK: {note.id} (version={note.version or 'draft'})\n")
    return 0


def cmd_bind(args, db: Session) -> int:
    from app.services.release_note_service import ReleaseNoteService
    try:
        n = ReleaseNoteService(db).publish_drafts(args.version)
    except ValueError as e:
        sys.stderr.write(f"Ошибка: {e}\n")
        return 2
    sys.stdout.write(f"Привязано {n} заметок к {args.version}\n")
    return 0


def _maybe_fix_win32_encoding() -> None:
    """Принудительно UTF-8 на Windows-консоли. Вызывается только из __main__."""
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


def main(argv: Optional[list[str]] = None, db: Optional[Session] = None) -> int:

    p = argparse.ArgumentParser(description="Release notes CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="Добавить запись (черновик или ретро)")
    p_add.add_argument("--type", required=True, choices=["new", "improvement", "fix"])
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
    if db is None:
        db = _get_db()
        try:
            return args.func(args, db)
        finally:
            db.close()
    return args.func(args, db)


if __name__ == "__main__":
    _maybe_fix_win32_encoding()
    raise SystemExit(main())
