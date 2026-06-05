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
from app.schemas.hours_balance import (
    HoursBalanceResponse,
    PeriodInfo,
    TeamSummary,
    EmployeeBalance,
    EmployeeBalanceDetail,
    EmployeeInfo,
    EmployeeKpi,
    MonthlySummary,
    DailyEntry,
)
from app.services.analytics_service import AnalyticsService, parse_teams_csv
from app.services.export_service import ExportService
from app.services.hours_balance_service import HoursBalanceService
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam


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


# === Hours balance endpoints ===


@router.get("/dashboard/hours-balance", response_model=HoursBalanceResponse)
def dashboard_hours_balance(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    teams: Optional[str] = Query(None, description="Команды CSV"),
    db: Session = Depends(get_db),
):
    """Виджет баланс часов команды: переработки/автоотгулы по сотрудникам."""
    today = date.today()
    resolved_from = from_ or date(today.year, 1, 1)
    resolved_to = to or today

    team_ids = parse_teams_csv(teams)

    if team_ids:
        employee_ids = (
            db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.team.in_(team_ids))
            .distinct()
            .all()
        )
        employee_ids = [row[0] for row in employee_ids]
    else:
        employee_ids = [
            row[0]
            for row in db.query(Employee.id).filter(Employee.is_active == True).all()  # noqa: E712
        ]

    svc = HoursBalanceService(db)
    result = svc.compute_team(
        employee_ids=employee_ids,
        from_=resolved_from,
        to_=resolved_to,
    )

    return HoursBalanceResponse(
        period=PeriodInfo(
            from_=result.period_from,
            to=result.period_to,
            working_days=result.working_days,
        ),
        team_summary=TeamSummary(
            employees_count=result.team_summary_employees_count,
            overtime_hours=result.team_summary_overtime_hours,
            skip_hours=result.team_summary_skip_hours,
            net_balance=result.team_summary_net_balance,
        ),
        employees=[
            EmployeeBalance(
                id=e.id,
                full_name=e.full_name,
                role_label=e.role_label,
                avatar_url=e.avatar_url,
                initials=e.initials,
                balance_hours=e.balance_hours,
                overtime_days=e.overtime_days,
                overtime_hours=e.overtime_hours,
                skip_days=e.skip_days,
                skip_hours=e.skip_hours,
                sparkline=e.sparkline,
            )
            for e in result.employees
        ],
    )


@router.get("/dashboard/hours-balance/{employee_id}", response_model=EmployeeBalanceDetail)
def dashboard_hours_balance_employee(
    employee_id: str,
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    """Drill-in: посуточный баланс часов одного сотрудника."""
    today = date.today()
    resolved_from = from_ or date(today.year, 1, 1)
    resolved_to = to or today

    svc = HoursBalanceService(db)
    try:
        result = svc.compute_employee(
            employee_id=employee_id,
            from_=resolved_from,
            to_=resolved_to,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Employee not found")

    return EmployeeBalanceDetail(
        employee=EmployeeInfo(
            id=result.employee_id,
            full_name=result.full_name,
            role_label=result.role_label,
            team_label=result.team_label,
            avatar_url=result.avatar_url,
            initials=result.initials,
        ),
        period=PeriodInfo(
            from_=result.period_from,
            to=result.period_to,
            working_days=0,  # drill-in doesn't need working_days count
        ),
        kpi=EmployeeKpi(
            balance_hours=result.balance_hours,
            overtime_days=result.overtime_days,
            overtime_hours=result.overtime_hours,
            skip_days=result.skip_days,
            skip_hours=result.skip_hours,
        ),
        monthly=[
            MonthlySummary(
                year=m.year,
                month=m.month,
                label=m.label,
                balance=m.balance,
                overtime_days=m.overtime_days,
                skip_days=m.skip_days,
            )
            for m in result.monthly
        ],
        days=[
            DailyEntry(
                day=d.day,
                norm=d.norm,
                fact=d.fact,
                delta=d.delta,
                kind=d.kind,
                absence_label=d.absence_label,
            )
            for d in result.days
        ],
    )


