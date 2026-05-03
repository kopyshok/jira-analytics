"""ScheduledBlock — периоды, когда сотрудники/роли недоступны для проектной работы."""

from datetime import date
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee
    from app.models.role import Role


class ScheduledBlock(Base, TimestampMixin):
    """Заблокированный период для проектной работы (напр. закрытие месяца).

    Если employee_id=None и role_id=None — блок для всей команды.
    Если role_id задан — блок для всех сотрудников этой роли в команде.
    Если employee_id задан — блок только для конкретного сотрудника.
    """

    __tablename__ = "scheduled_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    team: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    role_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[Optional["Role"]] = relationship("Role")
    employee: Mapped[Optional["Employee"]] = relationship("Employee")
