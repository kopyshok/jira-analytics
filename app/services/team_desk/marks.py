"""Отметки «просмотрено»: постановка, снятие, отсев сгоревших."""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import TeamDeskMark


def mark_reviewed(
    db: Session,
    issue_id: str,
    flag: str,
    signature: str,
    comment: Optional[str],
    user_id: Optional[str],
) -> TeamDeskMark:
    """Отметить один признак одной задачи. Повторная отметка обновляет запись."""
    row = (
        db.query(TeamDeskMark)
        .filter(TeamDeskMark.issue_id == issue_id, TeamDeskMark.flag == flag)
        .first()
    )
    if row is None:
        row = TeamDeskMark(issue_id=issue_id, flag=flag)
        db.add(row)
    row.signature = signature or ""
    row.comment = comment
    row.created_by_user_id = user_id
    row.marked_at = datetime.utcnow()
    db.commit()
    return row


def unmark(db: Session, issue_id: str, flag: str) -> None:
    """Снять отметку — признак снова считается проблемным."""
    db.query(TeamDeskMark).filter(
        TeamDeskMark.issue_id == issue_id, TeamDeskMark.flag == flag
    ).delete(synchronize_session=False)
    db.commit()


def active_marks(
    db: Session,
    issue_ids: list[str],
    current_signatures: dict[tuple[str, str], str],
) -> dict[tuple[str, str], TeamDeskMark]:
    """Живые отметки: подпись совпала с текущей причиной.

    current_signatures — {(признак, задача): подпись сейчас}. Отметка, чья
    подпись разошлась, считается сгоревшей и удаляется: держать мёртвые записи
    незачем, а тимлид увидит признак заново.
    """
    if not issue_ids:
        return {}
    rows = db.query(TeamDeskMark).filter(TeamDeskMark.issue_id.in_(issue_ids)).all()
    alive: dict[tuple[str, str], TeamDeskMark] = {}
    burned: list[str] = []
    for row in rows:
        current = current_signatures.get((row.flag, row.issue_id))
        if current is None or current != row.signature:
            burned.append(row.id)
            continue
        alive[(row.issue_id, row.flag)] = row
    if burned:
        db.query(TeamDeskMark).filter(TeamDeskMark.id.in_(burned)).delete(
            synchronize_session=False
        )
        db.commit()
    return alive
