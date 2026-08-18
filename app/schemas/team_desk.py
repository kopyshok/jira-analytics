"""Схемы раздела «Рабочий стол тимлида»."""
from typing import Optional

from pydantic import BaseModel, Field


class DeskSettings(BaseModel):
    """Настройки раздела: группы статусов, пороги подсветки, типы задач."""

    status_groups: dict[str, list[str]]
    queue_statuses: list[str]
    wip_statuses: list[str] = Field(
        default_factory=lambda: ["В РАБОТЕ"],
        description="Статусы, в которых работа идёт руками — лимит одновременных задач",
    )
    hidden_statuses: list[str] = Field(
        default_factory=list, description="Статусы, которые раздел не показывает"
    )
    thresholds: dict[str, float]
    subtask_types: list[str]
    assignee_types: list[str]
    developer_roles: list[str] = Field(
        default_factory=lambda: ["dev"], description="Роли, попадающие в срез"
    )


class MarkRequest(BaseModel):
    """Отметить признак просмотренным."""

    flag: str = Field(..., description="Код признака")
    signature: str = Field("", description="Снимок причины на момент отметки")
    comment: Optional[str] = None


class DailyRateRequest(BaseModel):
    """Дневная норма «резиновой» задачи; пусто — снять признак."""

    hours: Optional[float] = Field(None, ge=0, le=24)
