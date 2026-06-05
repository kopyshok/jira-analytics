"""Pydantic схемы виджета баланса часов."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


DayKind = Literal["norm", "overtime", "skip", "absence", "holiday"]


class PeriodInfo(BaseModel):
    from_: date
    to: date
    working_days: int

    model_config = ConfigDict(populate_by_name=True)

    def model_dump(self, **kwargs):  # alias from_ → from in output
        d = super().model_dump(**kwargs)
        if "from_" in d:
            d["from"] = d.pop("from_")
        return d


class TeamSummary(BaseModel):
    employees_count: int
    overtime_hours: float
    skip_hours: float
    net_balance: float


class EmployeeBalance(BaseModel):
    id: str
    full_name: str
    role_label: str | None = None
    avatar_url: str | None = None
    initials: str
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float
    sparkline: list[float]


class HoursBalanceResponse(BaseModel):
    period: PeriodInfo
    team_summary: TeamSummary
    employees: list[EmployeeBalance]


class MonthlySummary(BaseModel):
    year: int
    month: int
    label: str
    balance: float
    overtime_days: int
    skip_days: int


class DailyEntry(BaseModel):
    day: date
    norm: float
    fact: float
    delta: float
    kind: DayKind
    absence_label: str | None = None


class EmployeeInfo(BaseModel):
    id: str
    full_name: str
    role_label: str | None = None
    team_label: str | None = None
    avatar_url: str | None = None
    initials: str


class EmployeeKpi(BaseModel):
    balance_hours: float
    overtime_days: int
    overtime_hours: float
    skip_days: int
    skip_hours: float


class EmployeeBalanceDetail(BaseModel):
    employee: EmployeeInfo
    period: PeriodInfo
    kpi: EmployeeKpi
    monthly: list[MonthlySummary]
    days: list[DailyEntry]
