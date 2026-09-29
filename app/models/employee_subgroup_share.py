"""Распределение сотрудника по группам внутри команды."""

from datetime import date as _date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class EmployeeSubgroupShare(Base, TimestampMixin):
    """Доля сотрудника в группе команды с даты.

    Запись распределения — все строки одного сотрудника в одной команде с
    одинаковой ``valid_from``; сумма ``percent`` = 100. Запись действует до
    ``valid_from`` следующей записи. ``valid_from = None`` — «с начала участия».

    Инварианты (сумма 100, группа этой команды, одна запись на дату)
    проверяет ``SubgroupShareService``: NULL в уникальном ключе не сравнивается.
    """

    __tablename__ = "employee_subgroup_shares"
    __table_args__ = (
        Index("ix_employee_subgroup_shares_emp_team", "employee_id", "team"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    team: Mapped[str] = mapped_column(String(100), nullable=False)
    valid_from: Mapped[Optional[_date]] = mapped_column(Date, nullable=True)
    subgroup_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("team_subgroups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    percent: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<EmployeeSubgroupShare {self.employee_id}:{self.team}@{self.valid_from} {self.subgroup_id}={self.percent}>"
