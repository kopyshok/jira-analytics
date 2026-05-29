"""Analytics API endpoints.

Иерархический отчёт + дашборд-виджеты.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.dashboard import (
    DashboardProjectsResponse,
    DashboardNormWorkResponse,
    DashboardCategoriesResponse,
)
from app.schemas.analytics_report import AnalyticsReportResponse, IssueWorklogItem
from app.services.analytics_service import AnalyticsService, parse_teams_csv
from app.services.export_service import ExportService


router = APIRouter()


# === Dashboard endpoints ===

@router.get("/dashboard/norm-work", response_model=DashboardNormWorkResponse)
def dashboard_norm_work(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды CSV"),
    db: Session = Depends(get_db),
):
    """Widget 2: план/факт нормированных работ за квартал/месяц."""
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_norm_work(year=year, quarter=quarter, month=month, teams=parse_teams_csv(teams))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard/categories", response_model=DashboardCategoriesResponse)
def dashboard_categories(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды CSV"),
    db: Session = Depends(get_db),
):
    """Widget 3: метрики по категориям работ за квартал/месяц."""
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_categories(year=year, quarter=quarter, month=month, teams=parse_teams_csv(teams))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/dashboard/projects", response_model=DashboardProjectsResponse)
def dashboard_projects(
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды CSV"),
    db: Session = Depends(get_db),
):
    """Widget 1: обзор проектов квартала из утверждённого сценария."""
    svc = AnalyticsService(db)
    try:
        return svc.get_dashboard_projects(
            year=year, quarter=quarter, month=month, teams=parse_teams_csv(teams)
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/report", response_model=AnalyticsReportResponse)
def get_analytics_report(
    year: int,
    quarter: int,
    month: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    teams: Optional[str] = None,
    employee_id: Optional[str] = None,
    task_query: Optional[str] = None,
    work_type_codes: Optional[str] = None,
    category_codes: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Иерархический отчёт Аналитики."""
    teams_list = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    wt_codes = [c.strip() for c in work_type_codes.split(",") if c.strip()] if work_type_codes else None
    cat_codes = [c.strip() for c in category_codes.split(",") if c.strip()] if category_codes else None
    return AnalyticsService(db).get_hierarchical_report(
        year=year, quarter=quarter, month=month,
        start_date=start_date, end_date=end_date,
        teams=teams_list, employee_id=employee_id,
        task_query=task_query, work_type_codes=wt_codes, category_codes=cat_codes,
    )


@router.get("/report/export.xlsx")
def export_report_xlsx(
    year: int,
    quarter: int,
    month: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    teams: Optional[str] = None,
    employee_id: Optional[str] = None,
    task_query: Optional[str] = None,
    work_type_codes: Optional[str] = None,
    category_codes: Optional[str] = None,
    columns: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """XLSX-выгрузка иерархического отчёта Аналитики с применёнными фильтрами."""
    teams_list = [t.strip() for t in teams.split(",") if t.strip()] if teams else None
    wt_codes = [c.strip() for c in work_type_codes.split(",") if c.strip()] if work_type_codes else None
    cat_codes = [c.strip() for c in category_codes.split(",") if c.strip()] if category_codes else None
    cols = [c.strip() for c in columns.split(",") if c.strip()] if columns else []

    report = AnalyticsService(db).get_hierarchical_report(
        year=year, quarter=quarter, month=month,
        start_date=start_date, end_date=end_date,
        teams=teams_list, employee_id=employee_id,
        task_query=task_query, work_type_codes=wt_codes, category_codes=cat_codes,
    )
    blob = ExportService(db).export_analytics_report_xlsx(report, cols)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=analytics_report.xlsx"},
    )


@router.get("/report/issue/{issue_id}/worklogs", response_model=list[IssueWorklogItem])
def get_issue_worklogs_endpoint(
    issue_id: str,
    start: date,
    end: date,
    db: Session = Depends(get_db),
):
    """Плоский список ворклогов по задаче за период."""
    return AnalyticsService(db).get_issue_worklogs(issue_id, start, end)


