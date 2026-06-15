"""Диспетчер виджетов публичного рабочего стола аналитика.

Каждый виджет — тонкий адаптер: вызывает существующий сервис со столом
сотрудника и возвращает простой словарь для фронтенда. Никакой новой
бизнес-логики — только сбор данных и проекция в контракт.
"""

from __future__ import annotations

import calendar as _cal
import json
from datetime import date, datetime, time, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.work_desk import WorkDesk

# Полный список ключей виджетов. Порядок — порядок отображения по умолчанию.
WIDGET_KEYS: tuple[str, ...] = (
    "my_tasks",
    "weekly_load",
    "my_conflicts",
    "hours_balance",
    "unlogged_days",
    "category_breakdown",
    "team_absences",
    "team_availability",
    "production_calendar",
    "quarter_deadlines",
    "external_help",
    "recent_changes",
)

_QUARTER_MONTHS: Dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}


# ──────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────


def _desk_teams(desk: WorkDesk) -> List[str]:
    """Команды сотрудника стола (из его membership)."""
    emp = desk.employee
    if emp is None:
        return []
    return [t.team for t in emp.teams if t.team]


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    months = _QUARTER_MONTHS[quarter]
    start = date(year, months[0], 1)
    last_month = months[-1]
    end = date(year, last_month, _cal.monthrange(year, last_month)[1])
    return start, end


def _find_recent_plan(db: Session, teams: List[str], year: int, quarter: int):
    """Самый свежий ResourcePlan команды стола за квартал, либо None.

    Сначала ищем рассчитанные планы (computed_at) за нужный квартал и команду.
    Возвращаем None — адаптеры отдают пустой контракт.
    """
    from app.models import ResourcePlan

    if not teams:
        return None
    q_variants = [str(quarter), f"Q{quarter}", f"q{quarter}"]
    rows = (
        db.execute(
            select(ResourcePlan)
            .where(
                ResourcePlan.team.in_(teams),
                ResourcePlan.year == year,
                ResourcePlan.quarter.in_(q_variants),
            )
            .order_by(
                ResourcePlan.computed_at.desc().nullslast(),
                ResourcePlan.created_at.desc(),
            )
        )
        .scalars()
        .all()
    )
    return rows[0] if rows else None


# ──────────────────────────────────────────────────────────────────────────
# Адаптеры виджетов
# ──────────────────────────────────────────────────────────────────────────


def _adapter_my_tasks(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Назначения текущего сотрудника в свежем ресурсном плане квартала."""
    from app.models import ResourcePlanAssignment

    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return {"tasks": []}

    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.employee_id == desk.employee_id,
            )
            .order_by(ResourcePlanAssignment.start_date)
        )
        .scalars()
        .all()
    )
    tasks: List[dict] = []
    for a in rows:
        item = a.backlog_item
        issue = item.issue if item is not None else None
        key = getattr(issue, "key", None)
        jira_url = None
        if key:
            jira_url = f"https://itgri.atlassian.net/browse/{key}"
        tasks.append(
            {
                "key": key,
                "title": item.title if item is not None else None,
                "phase": a.phase,
                "start_date": a.start_date.isoformat() if a.start_date else None,
                "end_date": a.end_date.isoformat() if a.end_date else None,
                "hours": float(a.hours_allocated or 0.0),
                "jira_url": jira_url,
            }
        )
    return {"tasks": tasks}


def _adapter_weekly_load(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """План/факт сотрудника по месяцам квартала (понедельная база отсутствует)."""
    from app.services.capacity_service import CapacityService

    try:
        qc = CapacityService(db).quarter_capacity(desk.employee_id, year, quarter)
    except ValueError:
        return {"months": []}
    months = [
        {
            "year": m.year,
            "month": m.month,
            "norm_hours": round(m.norm_hours, 1),
            "fact_hours": round(m.fact_hours, 1),
        }
        for m in qc.months
    ]
    return {"months": months}


def _adapter_my_conflicts(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Конфликты плана, относящиеся к сотруднику стола."""
    from app.models import ResourcePlanAssignment
    from app.models.plan_conflict import PlanConflict

    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return {"conflicts": []}

    # Конфликты привязаны либо напрямую к employee_id, либо к assignment
    # сотрудника (например QUARTER_OVERFLOW по его задаче).
    own_assignment_ids = {
        r[0]
        for r in db.execute(
            select(ResourcePlanAssignment.id).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.employee_id == desk.employee_id,
            )
        ).all()
    }
    rows = (
        db.execute(select(PlanConflict).where(PlanConflict.plan_id == plan.id))
        .scalars()
        .all()
    )
    conflicts: List[dict] = []
    for c in rows:
        if c.employee_id != desk.employee_id and c.assignment_id not in own_assignment_ids:
            continue
        conflicts.append(
            {
                "type": c.type,
                "window_start": c.window_start.isoformat() if c.window_start else None,
                "window_end": c.window_end.isoformat() if c.window_end else None,
                "metric_value": float(c.metric_value) if c.metric_value is not None else None,
                "message": c.message,
            }
        )
    return {"conflicts": conflicts}


def _employee_balance(db: Session, desk: WorkDesk):
    """EmployeeDetailResult с 1 января по сегодня для сотрудника стола."""
    from app.services.hours_balance_service import HoursBalanceService

    today = date.today()
    from_ = date(today.year, 1, 1)
    return HoursBalanceService(db).compute_employee(
        desk.employee_id, from_, today, teams_filter=_desk_teams(desk) or None
    )


def _adapter_hours_balance(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Накопительный баланс часов сотрудника с начала года."""
    result = _employee_balance(db, desk)
    days = [
        {
            "date": d.day.isoformat(),
            "kind": d.kind,
            "delta": round(d.delta, 1),
        }
        for d in result.days
    ]
    return {"balance_hours": round(result.balance_hours, 1), "days": days}


def _adapter_unlogged_days(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Рабочие дни без списанных часов (kind == 'skip')."""
    result = _employee_balance(db, desk)
    days = [
        {
            "date": d.day.isoformat(),
            "expected_hours": round(d.norm, 1),
        }
        for d in result.days
        if d.kind == "skip"
    ]
    return {"days": days}


def _adapter_category_breakdown(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Часы сотрудника по категориям работ за квартал."""
    from app.models import Category, Issue, Worklog

    q_start, q_end = _quarter_bounds(year, quarter)
    start_dt = datetime.combine(q_start, time.min)
    end_dt = datetime.combine(q_end, time.max)

    rows = (
        db.query(
            Issue.category.label("code"),
            func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
        )
        .join(Issue, Worklog.issue_id == Issue.id)
        .filter(
            Worklog.employee_id == desk.employee_id,
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
        )
        .group_by(Issue.category)
        .all()
    )
    if not rows:
        return {"categories": []}

    labels = {
        c.code: c.label
        for c in db.query(Category.code, Category.label).all()
    }
    categories = [
        {
            "label": labels.get(r.code, r.code) if r.code else "Без категории",
            "hours": round(float(r.hours or 0.0), 1),
        }
        for r in rows
    ]
    categories.sort(key=lambda x: x["hours"], reverse=True)
    return {"categories": categories}


def _adapter_team_absences(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Отсутствия сотрудников команд стола, пересекающие квартал."""
    from app.models import Absence, Employee
    from app.models.absence_reason import AbsenceReason
    from app.models.employee_team import EmployeeTeam

    teams = _desk_teams(desk)
    if not teams:
        return {"absences": []}

    q_start, q_end = _quarter_bounds(year, quarter)
    rows = (
        db.query(Absence, AbsenceReason, Employee)
        .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
        .join(Employee, Absence.employee_id == Employee.id)
        .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
        .filter(
            EmployeeTeam.team.in_(teams),
            Absence.start_date <= q_end,
            Absence.end_date >= q_start,
        )
        .distinct()
        .all()
    )
    absences = [
        {
            "employee_name": emp.display_name,
            "start_date": ab.start_date.isoformat(),
            "end_date": ab.end_date.isoformat(),
            "reason_label": reason.label,
            "color": reason.color,
        }
        for ab, reason, emp in rows
    ]
    return {"absences": absences}


def _adapter_team_availability(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Кто в команде занят на этой неделе (по свежему ресурсному плану)."""
    from app.models import ResourcePlanAssignment

    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return {"week_start": week_start.isoformat(), "members": []}

    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.employee_id.is_not(None),
                ResourcePlanAssignment.start_date <= week_end,
                ResourcePlanAssignment.end_date >= week_start,
            )
            .order_by(ResourcePlanAssignment.start_date)
        )
        .scalars()
        .all()
    )
    by_emp: Dict[str, dict] = {}
    for a in rows:
        emp = a.employee
        name = emp.display_name if emp is not None else a.employee_id
        item = a.backlog_item
        label = item.title if item is not None else a.phase
        entry = by_emp.setdefault(a.employee_id, {"name": name, "busy": []})
        entry["busy"].append(
            {
                "label": label,
                "start": a.start_date.isoformat() if a.start_date else None,
                "end": a.end_date.isoformat() if a.end_date else None,
            }
        )
    return {"week_start": week_start.isoformat(), "members": list(by_emp.values())}


def _adapter_production_calendar(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Производственный календарь квартала + остаток рабочих дней."""
    from app.services.production_calendar_service import ProductionCalendarService

    svc = ProductionCalendarService(db)
    q_start, q_end = _quarter_bounds(year, quarter)
    hours_map = svc.hours_in_range_map(q_start, q_end)
    workdays_map = svc.workdays_in_range_map(q_start, q_end)

    today = date.today()
    quarter_workdays = 0
    remaining_workdays = 0
    days: List[dict] = []
    cur = q_start
    while cur <= q_end:
        is_wd = workdays_map.get(cur, cur.weekday() < 5)
        h = hours_map.get(cur)
        if h is None:
            h = 8.0 if cur.weekday() < 5 else 0.0
        if is_wd:
            quarter_workdays += 1
            if cur >= today:
                remaining_workdays += 1
        kind = "workday" if is_wd else "weekend"
        days.append({"date": cur.isoformat(), "kind": kind, "hours": float(h)})
        cur += timedelta(days=1)
    return {
        "quarter_workdays": quarter_workdays,
        "remaining_workdays": remaining_workdays,
        "days": days,
    }


def _adapter_quarter_deadlines(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Инициативы бэклога команд стола со сроком (due_date) в квартале."""
    from app.models import BacklogItem, Issue

    teams = _desk_teams(desk)
    if not teams:
        return {"items": []}

    q_start, q_end = _quarter_bounds(year, quarter)
    start_dt = datetime.combine(q_start, time.min)
    end_dt = datetime.combine(q_end, time.max)

    rows = (
        db.query(BacklogItem, Issue)
        .join(Issue, BacklogItem.issue_id == Issue.id)
        .filter(
            Issue.team.in_(teams),
            Issue.due_date.is_not(None),
            Issue.due_date >= start_dt,
            Issue.due_date <= end_dt,
            BacklogItem.archived_at.is_(None),
        )
        .order_by(Issue.due_date)
        .all()
    )
    items = [
        {
            "key": issue.key,
            "title": item.title,
            "due_date": issue.due_date.date().isoformat() if issue.due_date else None,
            "status": issue.status,
        }
        for item, issue in rows
    ]
    return {"items": items}


def _adapter_external_help(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Свои часы vs часы на задачах чужих команд для сотрудника стола."""
    from app.models import Issue, Worklog

    teams = set(_desk_teams(desk))
    q_start, q_end = _quarter_bounds(year, quarter)
    start_dt = datetime.combine(q_start, time.min)
    end_dt = datetime.combine(q_end, time.max)

    rows = (
        db.query(
            Issue.team.label("team"),
            func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
        )
        .join(Issue, Worklog.issue_id == Issue.id)
        .filter(
            Worklog.employee_id == desk.employee_id,
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
        )
        .group_by(Issue.team)
        .all()
    )
    own_hours = 0.0
    alien_hours = 0.0
    by_team: List[dict] = []
    for r in rows:
        h = round(float(r.hours or 0.0), 1)
        if r.team and r.team in teams:
            own_hours += h
        else:
            alien_hours += h
            by_team.append({"team": r.team or "Без команды", "hours": h})
    by_team.sort(key=lambda x: x["hours"], reverse=True)
    return {
        "own_hours": round(own_hours, 1),
        "alien_hours": round(alien_hours, 1),
        "by_team": by_team,
    }


def _adapter_recent_changes(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Назначения сотрудника, изменённые после последнего просмотра стола."""
    from app.models import ResourcePlanAssignment

    if desk.last_viewed_at is None:
        return {"changes": []}

    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return {"changes": []}

    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.employee_id == desk.employee_id,
                ResourcePlanAssignment.updated_at > desk.last_viewed_at,
            )
            .order_by(ResourcePlanAssignment.updated_at.desc())
        )
        .scalars()
        .all()
    )
    changes: List[dict] = []
    for a in rows:
        item = a.backlog_item
        issue = item.issue if item is not None else None
        changes.append(
            {
                "key": getattr(issue, "key", None),
                "title": item.title if item is not None else None,
                "change": a.phase,
                "start_date": a.start_date.isoformat() if a.start_date else None,
                "end_date": a.end_date.isoformat() if a.end_date else None,
            }
        )
    return {"changes": changes}


# Реестр: ключ → адаптер.
_REGISTRY: Dict[str, Callable[[Session, WorkDesk, int, int], dict]] = {
    "my_tasks": _adapter_my_tasks,
    "weekly_load": _adapter_weekly_load,
    "my_conflicts": _adapter_my_conflicts,
    "hours_balance": _adapter_hours_balance,
    "unlogged_days": _adapter_unlogged_days,
    "category_breakdown": _adapter_category_breakdown,
    "team_absences": _adapter_team_absences,
    "team_availability": _adapter_team_availability,
    "production_calendar": _adapter_production_calendar,
    "quarter_deadlines": _adapter_quarter_deadlines,
    "external_help": _adapter_external_help,
    "recent_changes": _adapter_recent_changes,
}


def dispatch(db: Session, desk: WorkDesk, key: str, year: int, quarter: int) -> dict:
    """Вычислить данные одного виджета. ValueError если ключ неизвестен."""
    if key not in WIDGET_KEYS:
        raise ValueError(f"Unknown widget key: {key}")
    adapter = _REGISTRY[key]
    return adapter(db, desk, year, quarter)
