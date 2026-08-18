"""Дневная норма по «резиновой» задаче (рабочий стол тимлида)."""
from typing import Optional

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class TeamDeskDailyRate(Base, TimestampMixin):
    """Сколько часов в день разработчик тратит на длинную задачу.

    Такие задачи заводятся на месяц и работа по ним идёт понемногу каждый день.
    Полный остаток оценки в очередь ставить нельзя — он забьёт неделю целиком,
    хотя реально задача забирает норму в день. Значение ставит тимлид, в Jira
    его нет, синхронизация его не трогает.
    """

    __tablename__ = "team_desk_daily_rates"
    __table_args__ = (UniqueConstraint("issue_id", name="uq_team_desk_daily_rate"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hours: Mapped[float] = mapped_column(Float, nullable=False)
    created_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
