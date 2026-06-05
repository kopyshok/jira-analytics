"""Seed ленты «Что нового» из файлов в репозитории.

Источник правды — `release_notes/<version>.json`. При старте приложения
сидер читает все файлы и upsert'ит записи в БД.

Идемпотентность по `(version, title)`: повторный seed не дублирует.
Текстовые поля (`title`, `description`, `help_link`, `sort_order`, `note_type`,
`section`) синхронизируются с файлом — fix typo в файле доедет до прода.
Поле `is_hidden` НЕ перезаписывается: оно управляется через админку.

Формат файла:
    {
      "version": "v1.2.1",
      "notes": [
        {
          "type": "new|improvement|fix",
          "section": "<section code>",
          "title": "...",
          "description": "...",
          "sort_order": 0,
          "help_link": null   // опционально
        }
      ]
    }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.models.release_note import NOTE_TYPES, SECTIONS, ReleaseNote

logger = logging.getLogger(__name__)

_DEFAULT_DIR = Path(__file__).resolve().parents[2] / "release_notes"


class ReleaseNoteSeeder:
    """Применяет release_notes/*.json к БД. Идемпотентен."""

    def __init__(self, db: Session, source_dir: Path | None = None) -> None:
        self.db = db
        self.source_dir = source_dir or _DEFAULT_DIR

    def seed(self) -> dict[str, int]:
        """Прогнать все JSON-файлы. Возвращает счётчики created/updated/skipped."""
        stats = {"created": 0, "updated": 0, "unchanged": 0, "files": 0}
        if not self.source_dir.is_dir():
            logger.info("release_notes seed: directory %s missing, skip", self.source_dir)
            return stats

        for path in sorted(self.source_dir.glob("v*.json")):
            stats["files"] += 1
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.error("release_notes seed: invalid JSON in %s: %s", path, e)
                continue

            version = payload.get("version")
            notes = payload.get("notes") or []
            if not version:
                logger.error("release_notes seed: %s missing 'version'", path)
                continue

            for entry in notes:
                action = self._upsert(version, entry, path.name)
                stats[action] += 1

        self.db.commit()
        logger.info(
            "release_notes seed: %d files, +%d created, ~%d updated, =%d unchanged",
            stats["files"], stats["created"], stats["updated"], stats["unchanged"],
        )
        return stats

    def _upsert(self, version: str, entry: dict, filename: str) -> str:
        title = (entry.get("title") or "").strip()
        if not title:
            logger.error("release_notes seed: %s — empty title in %s", filename, version)
            return "unchanged"

        note_type = entry.get("type") or entry.get("note_type")
        section = entry.get("section")
        if note_type not in NOTE_TYPES:
            logger.error("release_notes seed: %s — bad type %r in %r", filename, note_type, title)
            return "unchanged"
        if section not in SECTIONS:
            logger.error("release_notes seed: %s — bad section %r in %r", filename, section, title)
            return "unchanged"

        description = (entry.get("description") or "").strip()
        help_link = entry.get("help_link")
        sort_order = int(entry.get("sort_order") or 0)

        existing: ReleaseNote | None = (
            self.db.query(ReleaseNote)
            .filter(ReleaseNote.version == version, ReleaseNote.title == title)
            .one_or_none()
        )

        if existing is None:
            self.db.add(ReleaseNote(
                version=version,
                note_type=note_type,
                section=section,
                title=title,
                description=description,
                help_link=help_link,
                sort_order=sort_order,
            ))
            return "created"

        changed = False
        for field, value in (
            ("note_type", note_type),
            ("section", section),
            ("description", description),
            ("help_link", help_link),
            ("sort_order", sort_order),
        ):
            if getattr(existing, field) != value:
                setattr(existing, field, value)
                changed = True
        return "updated" if changed else "unchanged"


def seed_from_files(db: Session, source_dir: Path | None = None) -> dict[str, int]:
    """Helper для одноразового вызова из lifespan / CLI."""
    return ReleaseNoteSeeder(db, source_dir).seed()


def known_versions(source_dir: Path | None = None) -> Iterable[str]:
    """Все версии, для которых есть файлы (по имени файла)."""
    src = source_dir or _DEFAULT_DIR
    if not src.is_dir():
        return []
    return sorted(p.stem for p in src.glob("v*.json"))
