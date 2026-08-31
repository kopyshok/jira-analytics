"""EmployeeTeam model - M:N employee ↔ team membership."""

from datetime import date as _date
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.employee import Employee


class EmployeeTeam(Base):
    """Членство сотрудника в команде.

    Сотрудник может состоять в нескольких командах (кросс-функциональные
    роли, матричный менеджмент). Основная команда (``is_primary=True``)
    используется для агрегаций Capacity (план/факт, % загрузки).

    Участие периодизовано: активно в день ``d``, если
    ``(joined_at is None or joined_at <= d) and (left_at is None or d < left_at)``.
    ``left_at`` — первый день ВНЕ команды. Периодов на одну пару
    сотрудник/команда может быть несколько (ушёл — вернулся), пересекаться
    они не должны.

    Инварианты enforce'ятся в EmployeeTeamService, а не в БД (SQLite не
    поддерживает partial unique index):
    - периоды одной пары сотрудник/команда не пересекаются;
    - на любую дату у сотрудника не более одной ``is_primary=True`` записи.
    """

    __tablename__ = "employee_teams"
    # Уникальность (employee_id, team) снята: одна пара может иметь несколько
    # непересекающихся периодов участия. Непересечение проверяется в сервисе.

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Группа внутри команды (реестр team_subgroups). Проставляется только
    # у команд с включённым признаком деления; иначе всегда None.
    subgroup_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("team_subgroups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    joined_at: Mapped[_date | None] = mapped_column(Date, nullable=True)
    left_at: Mapped[_date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    employee: Mapped["Employee"] = relationship(back_populates="teams")

    def __repr__(self) -> str:
        return f"<EmployeeTeam {self.employee_id}:{self.team}{' *' if self.is_primary else ''}>"
