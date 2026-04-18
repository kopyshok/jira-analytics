"""Employees API endpoints.

Список сотрудников для использования во фронтенде (выпадающие списки и т.п.).
"""

from datetime import datetime
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee


router = APIRouter()


class EmployeeResponse(BaseModel):
    id: str
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class EmployeeFromJiraRequest(BaseModel):
    jira_account_id: str
    display_name: str
    email: Optional[str] = None
    is_active: bool = True
    avatar_url: Optional[str] = None


class RecalcActiveResponse(BaseModel):
    activated: int
    deactivated: int
    total_active: int


@router.get("", response_model=List[EmployeeResponse])
def list_employees(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """Список сотрудников."""
    query = db.query(Employee).order_by(Employee.display_name)
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    return query.all()


@router.post("/from-jira", response_model=EmployeeResponse)
def employee_from_jira(
    req: EmployeeFromJiraRequest,
    db: Session = Depends(get_db),
):
    """Явное добавление сотрудника из Jira (автокомплит на фронте)."""
    existing = (
        db.query(Employee)
        .filter(Employee.jira_account_id == req.jira_account_id)
        .one_or_none()
    )
    if existing is None:
        existing = Employee(
            id=str(uuid.uuid4()),
            jira_account_id=req.jira_account_id,
            display_name=req.display_name,
            email=req.email,
            avatar_url=req.avatar_url,
            is_active=True,
            synced_at=datetime.utcnow(),
        )
        db.add(existing)
    else:
        existing.display_name = req.display_name
        existing.email = req.email
        existing.avatar_url = req.avatar_url
        existing.is_active = True
        existing.synced_at = datetime.utcnow()

    db.flush()
    # Snapshot before commit — commit expires attrs and a subsequent read
    # may hit a thread-rotated connection (see CLAUDE.md ORM caveat).
    response = EmployeeResponse.model_validate(existing)
    db.commit()
    return response


@router.post("/recalc-active", response_model=RecalcActiveResponse)
def recalc_active(db: Session = Depends(get_db)):
    """Пересчитать is_active для всех сотрудников на основе worklog'ов
    на задачи с категориями «Активный стек» ∪ «Архив квартальных задач»."""
    from app.services.employee_service import EmployeeService

    stats = EmployeeService(db).recalc_active_by_categories()
    return RecalcActiveResponse(
        activated=stats.activated,
        deactivated=stats.deactivated,
        total_active=stats.total_active,
    )
