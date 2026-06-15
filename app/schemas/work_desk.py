"""Pydantic schemas для рабочих столов аналитиков."""

from pydantic import BaseModel


class DeskEmployee(BaseModel):
    id: str
    display_name: str
    avatar_url: str | None = None


class DeskPeriod(BaseModel):
    year: int
    quarter: int


class DeskMeta(BaseModel):
    employee: DeskEmployee
    teams: list[str]
    enabled_widgets: list[str]
    period: DeskPeriod
