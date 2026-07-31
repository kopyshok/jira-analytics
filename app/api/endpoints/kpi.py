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
from app.services.kpi.kpi_service import (
    build_approval_payload,
    build_teams_summary,
    build_trend,
    fact_value,
    report_with_approvals,
    resolve_breakdown,
    save_approval,
    score_field_names,
    summarize_report,
)
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


def _issue_brief(issue: Issue, base_url: str, metric: Optional[KpiMetric] = None) -> dict:
    """Карточка задачи для расшифровки. Для «норматив к факту»/«балл к максимуму»
    добавляет само значение факта/балла — иначе в списке видно только задачу
    без причины, почему она туда попала (см. мелочи ревью Фазы 4)."""
    extra: dict = {}
    if metric is not None and metric.calc_kind == "norm_to_fact":
        extra["fact"] = fact_value(issue, metric)
    elif metric is not None and metric.calc_kind == "score_to_max":
        scores = [getattr(issue, n, None) for n in score_field_names(metric)]
        usable = [s for s in scores if s is not None]
        extra["score"] = round(sum(usable) / len(usable), 2) if usable else None
    return {
        "key": issue.key,
        "summary": issue.summary,
        "status": issue.status,
        "resolution": issue.resolution,
        "url": _issue_url(base_url, issue.key),
        **extra,
    }


def _worklog_brief(w: Worklog, base_url: str, late: bool) -> dict:
    issue = w.issue
    return {
        "id": w.id,
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


# === Направления (доступно всем ролям — фильтр раздела виден не только админу) ===

@router.get("/directions", response_model=list[str])
def list_directions(db: Session = Depends(get_db)) -> list[str]:
    """Уникальные продуктовые направления задач — источник для выпадающего списка
    фильтра отчёта. Раньше единственным источником был справочник атрибутов
    (только для админа), поэтому фильтр на фронте был обычным текстовым полем
    (см. ревью, ВАЖНО 7)."""
    rows = db.query(Issue.direction).filter(Issue.direction.isnot(None)).distinct().all()
    return sorted({v for (v,) in rows if v})


# === Отчёт и сводка ===

@router.get("/report")
def get_report(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> dict:
    """Отчёт KPI по людям выбранных команд за месяц, со сводкой по направлению.

    Утверждённые месяцы отдаются из снимка (BLOCKER 1) — правка весов профиля
    или норматива после утверждения на такой месяц не влияет.
    """
    team_list = _resolve_teams(db, teams)
    report = report_with_approvals(db, team_list, year, month, direction=direction)
    report["summary"] = summarize_report(report["rows"])
    return report


@router.get("/teams-summary")
def get_teams_summary(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    teams: Optional[str] = Query(None, description="Команды через запятую"),
    direction: Optional[str] = Query(None, description="Продуктовое направление"),
    db: Session = Depends(get_db),
) -> dict:
    """Итог по каждой команде за месяц плюс дельта к прошлому месяцу.

    Ограничено тем же набором команд, что и отчёт (см. ``_resolve_teams``) —
    раньше сводка всегда считала все команды сервиса целиком, независимо от
    фильтра, которым сужена таблица (см. ревью, ВАЖНО 11).
    """
    team_list = _resolve_teams(db, teams)
    rows = build_teams_summary(db, team_list, year, month, direction=direction)
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
    """Расшифровка метрики: задачи (или записи трудозатрат) числителя и знаменателя со ссылками в Jira.

    Использует тот же отбор, что и расчёт отчёта (``resolve_breakdown``) —
    отрезки участия в команде и подстановку всех команд при пустом фильтре.
    Раньше расшифровка резала период на весь месяц целиком, из-за чего дробь
    в отчёте и список задач под ней могли расходиться (BLOCKER 2).
    """
    metric = db.query(KpiMetric).filter(KpiMetric.code == metric_code).first()
    if metric is None:
        raise HTTPException(status_code=404, detail="Метрика не найдена")

    team_list = _resolve_teams(db, teams)
    base_url = _jira_base_url(db)
    result = resolve_breakdown(db, metric, account_id, year, month, team_list, direction)

    if result["unit"] == "worklogs":
        late_ids = result["late_ids"]
        numerator = [_worklog_brief(w, base_url, late=True) for w in result["numerator"]]
        denominator = [_worklog_brief(w, base_url, late=(w.id in late_ids)) for w in result["denominator"]]
    else:
        numerator = [_issue_brief(i, base_url, metric) for i in result["numerator"]]
        denominator = [_issue_brief(i, base_url, metric) for i in result["denominator"]]

    return {
        "metric_code": metric.code, "metric_name": metric.name,
        "numerator": numerator, "denominator": denominator,
        "numerator_count": len(numerator), "denominator_count": len(denominator),
    }


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

    points = build_trend(db, employee, team_list, year, month, months, direction=direction)
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
    Утверждение устойчиво к одновременному закрытию месяца двумя
    руководителями (``save_approval`` откатывает и перечитывает строку при
    конфликте уникального ограничения — см. ревью, ВАЖНО 3).
    """
    payload = json.dumps(build_approval_payload(db, body.team, body.year, body.month), ensure_ascii=False)
    approved_at = datetime.utcnow()
    # Имя — то, что видит руководитель на плашке утверждения; почта — запасной
    # вариант, если у пользователя почему-то не заполнено имя (см. находка 4).
    approved_by = current_user.display_name or current_user.email

    row = save_approval(db, body.team, body.year, body.month, approved_by, approved_at, payload)

    return KpiApprovalOut(
        team=body.team, year=body.year, month=body.month, approved=True,
        approved_by=row.approved_by, approved_at=row.approved_at.isoformat(),
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
    """Отчёт KPI в xlsx. Утверждённые месяцы выгружаются из снимка — как в отчёте (BLOCKER 1)."""
    team_list = _resolve_teams(db, teams)
    report = report_with_approvals(db, team_list, year, month, direction=direction)
    blob = export_report_xlsx(report)
    return Response(
        content=blob,
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f'attachment; filename="kpi_{year}_{month:02d}.xlsx"'},
    )
