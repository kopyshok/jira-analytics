"""Сервис ленты «Что нового»."""
import re

from sqlalchemy.orm import Session

from app.models.release_note import NOTE_TYPES, SECTIONS, ReleaseNote
from app.models.user import User


# SemVer-ish сравнение: "v1.10.0" > "v1.2.0".
def _ver_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.lstrip("v").split(".") if p.isdigit())


_VERSION_RE = re.compile(r"^v?\d+(\.\d+)*$")


def _validate_version(v: str) -> None:
    if not _VERSION_RE.match(v):
        raise ValueError(
            f"Версия должна быть в формате vN.N.N: {v!r}"
        )


class ReleaseNoteService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_draft(
        self,
        *,
        note_type: str,
        section: str,
        title: str,
        description: str,
        help_link: str | None = None,
        created_by: str | None = None,
    ) -> ReleaseNote:
        if note_type not in NOTE_TYPES:
            raise ValueError(f"Неизвестный тип записи: {note_type!r}")
        if section not in SECTIONS:
            raise ValueError(f"Неизвестный раздел: {section!r}")
        note = ReleaseNote(
            note_type=note_type,
            section=section,
            title=title.strip(),
            description=description.strip(),
            help_link=help_link,
            created_by=created_by,
        )
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note

    def publish_drafts(self, version: str) -> int:
        _validate_version(version)
        drafts = (
            self.db.query(ReleaseNote)
            .filter(ReleaseNote.version.is_(None))
            .all()
        )
        for n in drafts:
            n.version = version
        self.db.commit()
        return len(drafts)

    def list_published_versions(self) -> list[str]:
        rows = (
            self.db.query(ReleaseNote.version)
            .filter(ReleaseNote.version.isnot(None))
            .distinct()
            .all()
        )
        versions = [r[0] for r in rows]
        return sorted(versions, key=_ver_key)

    def unread_versions_for(self, user: User) -> list[str]:
        # Все версии, у которых есть хотя бы одна не-скрытая запись.
        rows = (
            self.db.query(ReleaseNote.version)
            .filter(
                ReleaseNote.version.isnot(None),
                ReleaseNote.is_hidden.is_(False),
            )
            .distinct()
            .all()
        )
        visible_versions = {r[0] for r in rows}
        baseline = user.last_seen_release_version
        base_key = _ver_key(baseline) if baseline else None
        unread = [
            v for v in visible_versions
            if base_key is None or _ver_key(v) > base_key
        ]
        return sorted(unread, key=_ver_key)

    def mark_user_seen(self, user: User, version: str) -> None:
        user.last_seen_release_version = version
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

    def notes_for_versions(
        self, versions: list[str], *, include_hidden: bool = False
    ) -> list[ReleaseNote]:
        q = self.db.query(ReleaseNote).filter(ReleaseNote.version.in_(versions))
        if not include_hidden:
            q = q.filter(ReleaseNote.is_hidden.is_(False))
        return q.order_by(ReleaseNote.version, ReleaseNote.sort_order, ReleaseNote.created_at).all()

    def list_drafts(self) -> list[ReleaseNote]:
        return (
            self.db.query(ReleaseNote)
            .filter(ReleaseNote.version.is_(None))
            .order_by(ReleaseNote.sort_order, ReleaseNote.created_at)
            .all()
        )
