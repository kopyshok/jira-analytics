"""Teams API endpoint.

Distinct список команд из локальной БД — объединение `Issue.team` и
`EmployeeTeam.team`. Используется как быстрый источник для глобального
фильтра команд в шапке (без обращения к Jira API).
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import EmployeeTeam, Issue


router = APIRouter()


@router.get("", response_model=List[str])
def list_teams(db: Session = Depends(get_db)) -> List[str]:
    """Уникальные имена команд из локальной БД (issues + employee memberships)."""
    issue_rows = db.query(Issue.team).filter(Issue.team.isnot(None)).distinct().all()
    membership_rows = db.query(EmployeeTeam.team).distinct().all()

    merged: set[str] = set()
    for (value,) in issue_rows + membership_rows:
        if value:
            merged.add(value)

    return sorted(merged)
