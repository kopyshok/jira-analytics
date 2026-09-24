"""Ответ «кандидаты в исполнители» — общий для фазы плана и строки сценария
(см. app/services/assignee_candidates.py)."""

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel


class CandidateOut(BaseModel):
    """Кандидат в исполнители."""

    employee_id: str
    display_name: str
    role: Optional[str] = None
    team: Optional[str] = None
    # Загрузка за квартал по всем опорным планам команд, %.
    load_pct: float = 0.0
    # Границы участия в команде внутри квартала; None — край покрыт.
    member_from: Optional[date] = None
    member_to: Optional[date] = None


class CandidateGroupOut(BaseModel):
    key: Literal["jira", "team", "other"]
    label: str
    employees: List[CandidateOut]
