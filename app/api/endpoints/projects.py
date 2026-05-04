"""Projects API endpoints.

Список синхронизированных проектов для использования во фронтенде.
"""

import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.services.llm.base import ConfigurationError
from app.services.project_summary_service import ProjectSummaryService
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


class IssueHoursSchema(BaseModel):
    key: str
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
    issue_hours_by_key: List[IssueHoursSchema] = []
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
    year: Optional[int] = Query(None, description="filter by approved scenario year"),
    quarter: Optional[int] = Query(None, description="filter by approved scenario quarter (1-4)"),
    db: Session = Depends(get_db),
):
    """Список проектов.

    Без year+quarter — все эпики с категорией quarterly_tasks/archive_target.
    С year+quarter — только эпики из approved scenario для данного квартала.
    """
    team_filter = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    items = ProjectsService(db).list_projects(
        team_filter=team_filter,
        category=category,
        status_category=status_category,
        search=search,
        year=year,
        quarter=quarter,
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


class WorkBreakdownGroupSchema(BaseModel):
    label: str
    child_keys: List[str]


class ProjectSummarySchema(BaseModel):
    goals: List[str]
    result_flow_blocks: List[dict]
    result_checklist: List[dict]
    status_text: str
    workload_summary: str
    work_breakdown: List[WorkBreakdownGroupSchema] = []
    generated_at: datetime
    model_used: str


def _serialize_summary(row) -> ProjectSummarySchema:
    return ProjectSummarySchema(
        goals=json.loads(row.goals_json),
        result_flow_blocks=json.loads(row.result_flow_json),
        result_checklist=json.loads(row.result_checklist_json),
        status_text=row.status_text,
        workload_summary=row.workload_summary,
        work_breakdown=json.loads(row.work_breakdown_json) if row.work_breakdown_json else [],
        generated_at=row.generated_at,
        model_used=row.model_used,
    )


@router.get("/{key}/summary", response_model=Optional[ProjectSummarySchema])
async def get_summary(key: str, db: Session = Depends(get_db)):
    """Текущий AI-саммари из кэша. Возвращает null если ещё не сгенерирован."""
    row = await ProjectSummaryService(db).get_summary(key)
    return _serialize_summary(row) if row else None


@router.post("/{key}/regenerate-summary", response_model=ProjectSummarySchema)
async def regenerate_summary(key: str, db: Session = Depends(get_db)):
    """Синхронная регенерация AI-саммари через LLM. Публикует SSE-событие после успеха."""
    import httpx
    from app.services.llm.openrouter import LLMResponseError
    try:
        row = await ProjectSummaryService(db).regenerate(key)
    except LLMResponseError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ConfigurationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        if status == 429:
            raise HTTPException(status_code=503, detail="LLM rate limit. Подождите минуту или смените модель в Настройках → AI.")
        raise HTTPException(status_code=503, detail=f"LLM ответил {status}. Проверьте ключ и модель в Настройках → AI.")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM не ответил за 30с. Попробуйте более быструю модель в Настройках → AI.")
    from app.services.event_bus import get_event_bus
    import asyncio
    bus = get_event_bus()
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(bus.publish({"type": "project_summary_generated", "key": key}))
    except RuntimeError:
        pass
    return _serialize_summary(row)


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

    issue_hours_by_key = [
        IssueHoursSchema(key=k, hours=h)
        for k, h in detail.issue_hours_by_key
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
        issue_hours_by_key=issue_hours_by_key,
        rating_quality=detail.rating_quality,
        rating_speed=detail.rating_speed,
        rating_result=detail.rating_result,
    )
