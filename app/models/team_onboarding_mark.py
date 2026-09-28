"""Отметка шага «Первые шаги» для команды."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamOnboardingMark(Base, TimestampMixin):
    """Шаг настройки команды закрыт: выполнен или пропущен.

    Строка на (команда, шаг). Авто-шаг получает строку ``source=auto`` в момент,
    когда условие впервые выполнилось, и дальше не пересчитывается — новые
    задачи не должны перекрашивать пройденный шаг. Нет строки — шаг не закрыт.
    """

    __tablename__ = "team_onboarding_marks"
    __table_args__ = (UniqueConstraint("team", "step", name="uq_team_onboarding_mark"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    step: Mapped[str] = mapped_column(String(50), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)  # done | skipped
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # auto | manual
    marked_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    marked_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
