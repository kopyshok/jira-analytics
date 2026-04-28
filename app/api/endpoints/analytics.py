"""Analytics API endpoints.

Отчёты по факту из worklog:
- Часы по сотрудникам, проектам, категориям, периодам
- Контекстные переключения
"""

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.dashboard import (
    DashboardProjectsResponse,
    DashboardNormWorkResponse,
    DashboardCategoriesResponse,
)
from app.services.analytics_service import AnalyticsService, NO_TEAM_TOKEN, parse_teams_csv


router = APIRouter()


# === Dashboard endpoints ===

@router.get("/dashboard/norm-work", response_model=DashboardNormWorkResponse)
def dashboard_norm_work(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Widget 2: план/факт нормированных работ за квартал/месяц."""
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_norm_work(year=year, quarter=quarter, month=month)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard/categories", response_model=DashboardCategoriesResponse)
def dashboard_categories(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Widget 3: метрики по категориям работ за квартал/месяц."""
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_categories(year=year, quarter=quarter, month=month)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard/projects", response_model=DashboardProjectsResponse)
def dashboard_projects(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Widget 1: обзор проектов квартала из утверждённого сценария."""
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_projects(year=year, quarter=quarter, month=month)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# === Response schemas ===

class AggregateRowResponse(BaseModel):
    key: str
    label: str
    total_hours: float
    worklog_count: int


class ContextSwitchRowResponse(BaseModel):
    employee_id: str
    employee_name: str
    total_worklogs: int
    distinct_projects: int
    distinct_categories: int
    switches: int


# === Endpoints ===

@router.get("/hours/by-employee", response_model=List[AggregateRowResponse])
async def hours_by_employee(
    start: Optional[datetime] = Query(None, description="Начало периода (ISO)"),
    end: Optional[datetime] = Query(None, description="Конец периода (ISO)"),
    employee_id: Optional[str] = Query(None, description="UUID сотрудника"),
    project_key: Optional[str] = Query(None, description="Ключ проекта, напр. AAA"),
    teams: Optional[str] = Query(None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"),
    db: Session = Depends(get_db),
):
    """Часы по сотрудникам за период."""
    service = AnalyticsService(db)
    teams_list = parse_teams_csv(teams)
    rows = service.hours_by_employee(
        start=start, end=end,
        employee_id=employee_id, project_key=project_key,
        teams=teams_list,
    )
    return [AggregateRowResponse(**row.__dict__) for row in rows]


@router.get("/hours/by-project", response_model=List[AggregateRowResponse])
async def hours_by_project(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    employee_id: Optional[str] = Query(None, description="UUID сотрудника"),
    project_key: Optional[str] = Query(None, description="Ключ проекта, напр. AAA"),
    teams: Optional[str] = Query(None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"),
    db: Session = Depends(get_db),
):
    """Часы по проектам за период."""
    service = AnalyticsService(db)
    teams_list = parse_teams_csv(teams)
    rows = service.hours_by_project(
        start=start, end=end,
        employee_id=employee_id, project_key=project_key,
        teams=teams_list,
    )
    return [AggregateRowResponse(**row.__dict__) for row in rows]


@router.get("/hours/by-category", response_model=List[AggregateRowResponse])
async def hours_by_category(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    employee_id: Optional[str] = Query(None, description="UUID сотрудника"),
    project_key: Optional[str] = Query(None, description="Ключ проекта, напр. AAA"),
    teams: Optional[str] = Query(None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"),
    db: Session = Depends(get_db),
):
    """Часы по управленческим категориям работ."""
    service = AnalyticsService(db)
    teams_list = parse_teams_csv(teams)
    rows = service.hours_by_category(
        start=start, end=end,
        employee_id=employee_id, project_key=project_key,
        teams=teams_list,
    )
    return [AggregateRowResponse(**row.__dict__) for row in rows]


@router.get("/hours/by-period", response_model=List[AggregateRowResponse])
async def hours_by_period(
    period: str = Query("day", pattern="^(day|week|month)$"),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    employee_id: Optional[str] = Query(None, description="UUID сотрудника"),
    project_key: Optional[str] = Query(None, description="Ключ проекта, напр. AAA"),
    teams: Optional[str] = Query(None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"),
    db: Session = Depends(get_db),
):
    """Часы по периодам: day, week, month."""
    service = AnalyticsService(db)
    teams_list = parse_teams_csv(teams)
    rows = service.hours_by_period(
        period=period, start=start, end=end,
        employee_id=employee_id, project_key=project_key,
        teams=teams_list,
    )
    return [AggregateRowResponse(**row.__dict__) for row in rows]


@router.get("/context-switching", response_model=List[ContextSwitchRowResponse])
async def context_switching(
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    employee_id: Optional[str] = Query(None, description="UUID сотрудника"),
    project_key: Optional[str] = Query(None, description="Ключ проекта, напр. AAA"),
    teams: Optional[str] = Query(None, description=f"Команды CSV, {NO_TEAM_TOKEN} = без команды"),
    db: Session = Depends(get_db),
):
    """Метрика контекстных переключений по сотрудникам."""
    service = AnalyticsService(db)
    teams_list = parse_teams_csv(teams)
    rows = service.context_switching(
        start=start, end=end,
        employee_id=employee_id, project_key=project_key,
        teams=teams_list,
    )
    return [ContextSwitchRowResponse(**row.__dict__) for row in rows]
