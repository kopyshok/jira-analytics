"""EmployeeTeam model - M:N employee ↔ team membership."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import generate_uuid
from app.database import Base


class EmployeeTeam(Base):
    """Членство сотрудника в команде.

    Сотрудник может состоять в нескольких командах (кросс-функциональные
    роли, матричный менеджмент). Ровно одна из записей для данного
    employee_id должна иметь ``is_primary=True`` — она используется для
    агрегаций Capacity (план/факт, % загрузки).

    Инвариант single-primary enforce'ится в EmployeeTeamService, а не в БД:
    SQLite не поддерживает partial unique index.
    """

    __tablename__ = "employee_teams"
    __table_args__ = (
        UniqueConstraint("employee_id", "team", name="uq_employee_teams_employee_team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    employee = relationship("Employee", back_populates="teams")

    def __repr__(self) -> str:
        return f"<EmployeeTeam {self.employee_id}:{self.team}{' *' if self.is_primary else ''}>"
