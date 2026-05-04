"""Pydantic-схемы AI-результата."""
from typing import Literal
from pydantic import BaseModel, Field


WorkBucket = Literal["analysis", "development", "testing", "ope"]


class ChecklistItem(BaseModel):
    """Достижение проекта. `category` привязывает к bucket'у из `work_breakdown`."""
    label: str = Field(max_length=120)
    done: bool = False
    category: WorkBucket


class WorkBreakdownGroup(BaseModel):
    """Группа трудозатрат: bucket — характер работ (4 типа для цвета),
    label — содержательная формулировка КОНКРЕТНОЙ работы.
    Допустимо несколько групп с одинаковым bucket."""
    bucket: WorkBucket
    label: str = Field(max_length=80)
    child_keys: list[str] = Field(default_factory=list, max_length=50)


class ProjectSummary(BaseModel):
    """Структурированный AI-результат: цели, чек-лист, статус, нагрузка, разбивка."""
    goals: list[str] = Field(min_length=1, max_length=5)
    result_checklist: list[ChecklistItem] = Field(min_length=0, max_length=8)
    status_text: str
    workload_summary: str
    work_breakdown: list[WorkBreakdownGroup] = Field(default_factory=list, max_length=8)
