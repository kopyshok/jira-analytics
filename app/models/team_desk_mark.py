"""Отметка «просмотрено» на признаке задачи (рабочий стол тимлида)."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamDeskMark(Base, TimestampMixin):
    """Тимлид посмотрел признак и решил, что это не проблема.

    Отметка живёт, пока не изменилась причина: `signature` — снимок причины на
    момент отметки (статус для «зависла», оценка и факт для «перерасхода»).
    Подпись разошлась с текущей — отметка сгорела, признак снова проблемный.
    Иначе отметка навсегда прятала бы реальную проблему.
    """

    __tablename__ = "team_desk_marks"
    __table_args__ = (UniqueConstraint("issue_id", "flag", name="uq_team_desk_mark"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    flag: Mapped[str] = mapped_column(String(32), nullable=False)
    signature: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
