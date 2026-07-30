"""Раздел KPI: отчёт, расшифровка метрики, тренд, утверждение месяца, выгрузка.

Роутер только валидирует вход, зовёт сервисы ``app.services.kpi.kpi_service``
и формирует ответ — никакого расчёта здесь нет (см. ``app/api/CLAUDE.md``).
"""
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.endpoints.teams import list_teams
from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.employee import Employee
from app.models.kpi import KpiApproval, KpiMetric
from app.models.issue import Issue
from app.models.user import User
from app.models.worklog import Worklog
from app.services.analytics_service import parse_teams_csv
from app.services.kpi.conditions import ConditionSet, build_issue_query
from app.services.kpi.kpi_service import (
    build_report,
    compute_employee_month,
    month_bounds,
    previous_month,
    summarize_report,
    with_direction,
    worklog_items,
)
from app.services.kpi.settings import read_kpi_settings
from app.services.kpi.xlsx_export import export_report_xlsx

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# === Schemas ===

class KpiApproveRequest(BaseModel):
    team: str
    year: int
    month: int


class KpiApprovalOut(BaseModel):
    team: str
    year: int
    month: int
    approved: bool
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None


# === Helpers ===

def _jira_base_url(db: Session) -> str:
    """Базовый URL Jira-инстанса — для ссылок на задачи в расшифровке."""
    row = db.query(AppSetting).filter(AppSetting.key == "jira_base_url").first()
    return ((row.value if row else "") or "").rstrip("/")


def _issue_url(base_url: str, key: str) -> Optional[str]:
    return f"{base_url}/browse/{key}" if base_url else None


def _issue_brief(issue: Issue, base_url: str) -> dict:
    return {
        "key": issue.key,
        "summary": issue.summary,
        "status": issue.status,
        "resolution": issue.resolution,
        "url": _issue_url(base_url, issue.key),
    }


def _worklog_brief(w: Worklog, base_url: str, late: bool) -> dict:
    issue = w.issue
    return {
        "key": issue.key if issue else None,
        "summary": issue.summary if issue else None,
        "started_at": w.started_at.isoformat() if w.started_at else None,
        "jira_created_at": w.jira_created_at.isoformat() if w.jira_created_at else None,
        "hours": w.hours,
        "late": late,
        "url": _issue_url(base_url, issue.key) if issue else None,
    }


def _resolve_teams(db: Session, teams_csv: Optional[str]) -> list[str]:
    """Команды из query-параметра; если не заданы — все команды, известные сервису."""
    parsed = parse_teams_csv(teams_csv)
    return parsed or list_teams(db)


# === Отчёт и сводка ===

@router.get("/report")
def get_report(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> dict:
    """Отчёт KPI по людям выбранных команд за месяц, со сводкой по направлению."""
    team_list = _resolve_teams(db, teams)
    report = build_report(db, team_list, year, month, direction=direction)
    report["summary"] = summarize_report(report["rows"])
    return report


@router.get("/teams-summary")
def get_teams_summary(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> dict:
    """Итог по каждой команде за месяц плюс дельта к прошлому месяцу."""
    teams = list_teams(db)
    prev_year, prev_month = previous_month(year, month)

    rows = []
    for team in teams:
        current = summarize_report(build_report(db, [team], year, month, direction=direction)["rows"])
        prior = summarize_report(build_report(db, [team], prev_year, prev_month, direction=direction)["rows"])
        delta = (
            current["avg_total"] - prior["avg_total"]
            if current["avg_total"] is not None and prior["avg_total"] is not None
            else None
        )
        rows.append({
            "team": team,
            "avg_total": current["avg_total"],
            "below_target_count": current["below_target_count"],
            "no_data_metrics_count": current["no_data_metrics_count"],
            "delta": delta,
        })
    return {"year": year, "month": month, "rows": rows}


# === Расшифровка метрики ===

@router.get("/breakdown")
def get_breakdown(
    account_id: str = Query(...),
    metric_code: str = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> dict:
    """Расшифровка метрики: задачи (или записи трудозатрат) числителя и знаменателя со ссылками в Jira."""
    metric = db.query(KpiMetric).filter(KpiMetric.code == metric_code).first()
    if metric is None:
        raise HTTPException(status_code=404, detail="Метрика не найдена")

    team_list = parse_teams_csv(teams)
    period_start, period_end = month_bounds(year, month)
    periods = [(period_start, period_end)]
    base_url = _jira_base_url(db)
    settings = read_kpi_settings(db)
    num_cs = with_direction(ConditionSet.from_json(metric.numerator_json), direction)

    if num_cs.unit == "worklogs":
        on_time, late = worklog_items(db, num_cs, account_id, periods, team_list, settings)
        numerator = [_worklog_brief(w, base_url, late=True) for w in late]
        denominator = [_worklog_brief(w, base_url, late=False) for w in on_time] + numerator
        return {"metric_code": metric.code, "metric_name": metric.name,
                "numerator": numerator, "denominator": denominator}

    num_q = build_issue_query(db, num_cs, account_id, periods,
                              settings.excluded_statuses, team_list)
    numerator = [_issue_brief(i, base_url) for i in num_q.all()]

    denominator = []
    if metric.calc_kind == "ratio":
        den_cs = with_direction(ConditionSet.from_json(metric.denominator_json), direction)
        den_q = build_issue_query(db, den_cs, account_id, periods,
                                  settings.excluded_statuses, team_list)
        denominator = [_issue_brief(i, base_url) for i in den_q.all()]

    return {"metric_code": metric.code, "metric_name": metric.name,
            "numerator": numerator, "denominator": denominator}


# === Тренд сотрудника ===

@router.get("/trend")
def get_trend(
    account_id: str = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    months: int = Query(6, ge=1, le=24),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> dict:
    """Итог и метрики сотрудника за последние N месяцев — для графика в карточке."""
    employee = db.query(Employee).filter(Employee.jira_account_id == account_id).first()
    if employee is None:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")

    team_list = parse_teams_csv(teams)
    if not team_list and employee.team:
        team_list = [employee.team]
    settings = read_kpi_settings(db)

    points = []
    y, m = year, month
    for _ in range(months):
        row = compute_employee_month(db, employee, team_list, y, m, settings=settings, direction=direction)
        points.append({"year": y, "month": m, **row})
        y, m = previous_month(y, m)
    points.reverse()
    return {"account_id": account_id, "points": points}


# === Утверждение месяца ===

@router.post("/approve", response_model=KpiApprovalOut)
def approve_month(
    body: KpiApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KpiApprovalOut:
    """Заморозить снимок месяца: результат вместе с весами и правилами на момент утверждения.

    Повторное утверждение того же месяца перезаписывает существующий снимок
    (уникальное ограничение team+year+month не должно приводить к ошибке).
    """
    report = build_report(db, [body.team], body.year, body.month)
    payload = json.dumps(report, ensure_ascii=False)
    approved_at = datetime.utcnow()
    approved_by = current_user.email

    row = (
        db.query(KpiApproval)
        .filter_by(team=body.team, year=body.year, month=body.month)
        .first()
    )
    if row is None:
        db.add(KpiApproval(
            team=body.team, year=body.year, month=body.month,
            approved_by=approved_by, approved_at=approved_at, payload_json=payload,
        ))
    else:
        row.approved_by = approved_by
        row.approved_at = approved_at
        row.payload_json = payload
    db.commit()

    return KpiApprovalOut(
        team=body.team, year=body.year, month=body.month, approved=True,
        approved_by=approved_by, approved_at=approved_at.isoformat(),
    )


@router.get("/approval", response_model=KpiApprovalOut)
def get_approval(
    team: str = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
) -> KpiApprovalOut:
    """Кто и когда утвердил месяц; если ещё не утверждён — ``approved: false``."""
    row = db.query(KpiApproval).filter_by(team=team, year=year, month=month).first()
    if row is None:
        return KpiApprovalOut(team=team, year=year, month=month, approved=False)
    return KpiApprovalOut(
        team=team, year=year, month=month, approved=True,
        approved_by=row.approved_by, approved_at=row.approved_at.isoformat(),
    )


# === Выгрузка ===

@router.get("/export.xlsx", responses={200: {"content": {XLSX_MIME: {}}}})
def export_xlsx(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> Response:
    """Отчёт KPI в xlsx."""
    team_list = _resolve_teams(db, teams)
    report = build_report(db, team_list, year, month, direction=direction)
    blob = export_report_xlsx(report)
    return Response(
        content=blob,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="kpi_{year}_{month:02d}.xlsx"'},
    )
