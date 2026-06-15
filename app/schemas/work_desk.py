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


class WorkDeskCreate(BaseModel):
    employee_id: str
    enabled_widgets: list[str] = []


class WorkDeskWidgetsUpdate(BaseModel):
    enabled_widgets: list[str] = []


class WorkDeskCreated(BaseModel):
    """Ответ на создание/перевыпуск — содержит свежий токен."""

    id: str
    token: str
    employee_id: str
    enabled_widgets: list[str]


class WorkDeskListItem(BaseModel):
    """Стол в списке для управления (присоединяется к списку сотрудников на фронте)."""

    id: str
    employee: DeskEmployee
    status: str  # "active" | "none"
    token: str | None
    enabled_widgets: list[str]
    desk_url_path: str | None
