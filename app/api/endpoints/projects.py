"""Projects API endpoints.

Список синхронизированных проектов для использования во фронтенде.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.services.projects_service import ProjectsService


router = APIRouter()


class ProjectResponse(BaseModel):
    id: str
    key: str
    name: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("/all", response_model=List[ProjectResponse])
def list_projects(
    is_active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
):
    """Список синхронизированных Jira-проектов (для backlog и т.п.)."""
    query = db.query(Project).order_by(Project.key)
    if is_active is not None:
        query = query.filter(Project.is_active == is_active)
    return query.all()


# ---------------------------------------------------------------------------
# New schemas for quarterly projects page
# ---------------------------------------------------------------------------

class ProjectListItemSchema(BaseModel):
    key: str
    summary: str
    status: str
    status_category: Optional[str] = None
    category: str
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    total_hours: float
    child_count: int
    employee_count: int
    rating_quality: Optional[int] = None
    rating_speed: Optional[int] = None
    rating_result: Optional[int] = None


class CategoryBreakdownSchema(BaseModel):
    code: str
    label: str
    color: Optional[str] = None
    hours: float
    pct: float


class EmployeeBreakdownSchema(BaseModel):
    employee_id: str
    name: str
    hours: float
    pct: float


class TopIssueSchema(BaseModel):
    key: str
    summary: str
    hours: float


class ProjectDetailSchema(BaseModel):
    key: str
    summary: str
    description: Optional[str] = None
    status: str
    status_category: Optional[str] = None
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    planned_start_date: Optional[datetime] = None
    planned_end_date: Optional[datetime] = None
    total_hours: float
    weeks: float
    child_count: int
    employee_count: int
    categories: List[CategoryBreakdownSchema]
    employees: List[EmployeeBreakdownSchema]
    top_issues: List[TopIssueSchema]
    rating_quality: Optional[int] = None
    rating_speed: Optional[int] = None
    rating_result: Optional[int] = None


# ---------------------------------------------------------------------------
# New endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[ProjectListItemSchema])
def list_quarterly_projects(
    teams: Optional[str] = Query(None, description="comma-separated team names"),
    category: Optional[str] = Query(None, description="quarterly_tasks | archive_target"),
    status_category: Optional[str] = Query(None, description="new | indeterminate | done"),
    search: Optional[str] = Query(None, description="search by key/summary"),
    db: Session = Depends(get_db),
):
    """Список проектов (parent issues с категорией quarterly_tasks или archive_target)."""
    team_filter = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    items = ProjectsService(db).list_projects(
        team_filter=team_filter,
        category=category,
        status_category=status_category,
        search=search,
    )
    total_hours_map = {item.key: item.total_hours for item in items}

    result = []
    for item in items:
        result.append(ProjectListItemSchema(
            key=item.key,
            summary=item.summary,
            status=item.status,
            status_category=item.status_category,
            category=item.category,
            period_start=item.period_start,
            period_end=item.period_end,
            total_hours=item.total_hours,
            child_count=item.child_count,
            employee_count=item.employee_count,
            rating_quality=item.rating_quality,
            rating_speed=item.rating_speed,
            rating_result=item.rating_result,
        ))
    return result


@router.get("/{key}", response_model=ProjectDetailSchema)
def get_project(key: str, db: Session = Depends(get_db)):
    """Детальный блок для страницы анализа проекта."""
    detail = ProjectsService(db).get_project_detail(key)
    if not detail:
        raise HTTPException(status_code=404, detail="Project not found")

    total_hours = detail.total_hours or 0.0

    categories = [
        CategoryBreakdownSchema(
            code=c.code,
            label=c.label,
            color=c.color,
            hours=c.hours,
            pct=round(c.hours / total_hours * 100, 1) if total_hours else 0.0,
        )
        for c in detail.categories
    ]
    employees = [
        EmployeeBreakdownSchema(
            employee_id=e.employee_id,
            name=e.name,
            hours=e.hours,
            pct=round(e.hours / total_hours * 100, 1) if total_hours else 0.0,
        )
        for e in detail.employees
    ]
    top_issues = [
        TopIssueSchema(
            key=t.key,
            summary=t.summary,
            hours=t.hours,
        )
        for t in detail.top_issues
    ]

    return ProjectDetailSchema(
        key=detail.key,
        summary=detail.summary,
        description=detail.description,
        status=detail.status,
        status_category=detail.status_category,
        period_start=detail.period_start,
        period_end=detail.period_end,
        planned_start_date=detail.planned_start_date,
        planned_end_date=detail.planned_end_date,
        total_hours=total_hours,
        weeks=detail.weeks or 0.0,
        child_count=detail.child_count,
        employee_count=detail.employee_count,
        categories=categories,
        employees=employees,
        top_issues=top_issues,
        rating_quality=detail.rating_quality,
        rating_speed=detail.rating_speed,
        rating_result=detail.rating_result,
    )
