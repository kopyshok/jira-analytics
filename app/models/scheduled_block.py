"""ScheduledBlock — периоды, когда сотрудники/роли недоступны для проектной работы."""

from datetime import date
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy import Date, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scheduled_block_role import ScheduledBlockRole
    from app.models.scheduled_block_employee import ScheduledBlockEmployee


class ScheduledBlock(Base, TimestampMixin):
    """Заблокированный период для проектной работы (напр. закрытие месяца).

    Если roles=[] и employees=[] — блок для всей команды
    (или для всех сотрудников, если team=None).
    Иначе блок действует на объединение: все сотрудники указанных ролей
    + перечисленные конкретные сотрудники.
    """

    __tablename__ = "scheduled_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    roles: Mapped[List["ScheduledBlockRole"]] = relationship(
        "ScheduledBlockRole",
        cascade="all, delete-orphan",
    )
    employees: Mapped[List["ScheduledBlockEmployee"]] = relationship(
        "ScheduledBlockEmployee",
        cascade="all, delete-orphan",
    )
