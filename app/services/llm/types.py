"""Pydantic-схемы AI-результата."""
from typing import Literal
from pydantic import BaseModel, Field


class FlowBlock(BaseModel):
    label: str
    status: Literal["source", "flow", "done"] = "flow"


class ChecklistItem(BaseModel):
    label: str
    done: bool = True


class ProjectSummary(BaseModel):
    """Структурированный AI-результат: цели, flow, чек-лист, статус, нагрузка."""
    goals: list[str] = Field(min_length=1, max_length=5)
    result_flow_blocks: list[FlowBlock] = Field(min_length=1, max_length=6)
    result_checklist: list[ChecklistItem] = Field(min_length=0, max_length=6)
    status_text: str
    workload_summary: str
