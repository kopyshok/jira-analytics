"""Диспетчер виджетов публичного рабочего стола аналитика.

Каждый виджет — тонкий адаптер: вызывает существующий сервис со столом
сотрудника и возвращает простой словарь для фронтенда. Никакой новой
бизнес-логики — только сбор данных и проекция в контракт.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, time, timedelta
from typing import Callable, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.work_desk import WorkDesk

# Полный список ключей виджетов. Порядок — порядок отображения по умолчанию.
WIDGET_KEYS: tuple[str, ...] = (
    "my_tasks",
    "my_timeline",
    "hours_balance",
    "category_breakdown",
    "team_absences",
    "team_availability",
    "production_calendar",
    "awaiting_reaction",
)

_QUARTER_MONTHS: Dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}

_JIRA_BROWSE = "https://itgri.atlassian.net/browse/"

# Фаза назначения → поле плановой оценки на BacklogItem.
_PHASE_ESTIMATE_FIELD: Dict[str, str] = {
    "analyst": "estimate_analyst_hours",
    "dev": "estimate_dev_hours",
    "qa": "estimate_qa_hours",
    "opo": "estimate_opo_hours",
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


def _jira_url(key: Optional[str]) -> Optional[str]:
    return f"{_JIRA_BROWSE}{key}" if key else None


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


def _worklog_fact_map(
    db: Session,
    pairs: List[tuple[str, str]],
    q_start: date,
    q_end: date,
) -> Dict[tuple[str, str], float]:
    """Сумма Worklog.hours по парам (employee_id, issue_id) за квартал.

    Один сгруппированный запрос на все пары — без N+1. Окно конкретного
    назначения сужается вызывающим кодом (он знает start/end ассайнмента).
    """
    if not pairs:
        return {}
    from app.models import Worklog

    emp_ids = {p[0] for p in pairs}
    issue_ids = {p[1] for p in pairs}
    start_dt = datetime.combine(q_start, time.min)
    end_dt = datetime.combine(q_end, time.max)
    rows = (
        db.query(
            Worklog.employee_id,
            Worklog.issue_id,
            func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
        )
        .filter(
            Worklog.employee_id.in_(emp_ids),
            Worklog.issue_id.in_(issue_ids),
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
        )
        .group_by(Worklog.employee_id, Worklog.issue_id)
        .all()
    )
    return {(r.employee_id, r.issue_id): float(r.hours or 0.0) for r in rows}


def _assignment_projects(
    db: Session,
    plan_id: str,
    employee_id: str,
    q_start: date,
    q_end: date,
) -> List[dict]:
    """Список проектов/назначений сотрудника в плане (контракт my_tasks).

    Факт-часы берутся одним сгруппированным запросом по всем задачам
    сотрудника, затем при необходимости пересчитываются по окну назначения.
    """
    from app.models import ResourcePlanAssignment

    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.employee_id == employee_id,
            )
            .order_by(ResourcePlanAssignment.start_date)
        )
        .scalars()
        .all()
    )
    # Собираем (emp, issue) пары для квартального факта одним запросом.
    pairs: List[tuple[str, str]] = []
    issue_by_assignment: Dict[str, object] = {}
    for a in rows:
        item = a.backlog_item
        issue = item.issue if item is not None else None
        issue_by_assignment[a.id] = issue
        if issue is not None:
            pairs.append((employee_id, issue.id))
    quarter_fact = _worklog_fact_map(db, pairs, q_start, q_end)

    projects: List[dict] = []
    for a in rows:
        issue = issue_by_assignment.get(a.id)
        key = getattr(issue, "key", None)
        norm = _assignment_norm(a)

        if issue is None:
            fact = 0.0
        elif a.start_date and a.end_date:
            # Сужаем факт до окна назначения отдельным точечным запросом —
            # назначений у одного сотрудника немного, N+1 здесь не критичен.
            fact = _issue_fact_in_window(db, employee_id, issue.id, a.start_date, a.end_date)
        else:
            fact = quarter_fact.get((employee_id, issue.id), 0.0)

        pct = round(fact / norm * 100) if norm > 0 else 0
        projects.append(
            {
                "key": key,
                "issue_id": getattr(issue, "id", None),
                "title": a.backlog_item.title if a.backlog_item is not None else None,
                "jira_url": _jira_url(key),
                "status": getattr(issue, "status", None),
                "start_date": a.start_date.isoformat() if a.start_date else None,
                "end_date": a.end_date.isoformat() if a.end_date else None,
                "norm_hours": round(norm, 1),
                "fact_hours": round(fact, 1),
                "pct": pct,
            }
        )
    return projects


def _project_children(
    db: Session,
    employee_id: str,
    issue_ids: List[str],
    q_start: date,
    q_end: date,
) -> Dict[str, List[dict]]:
    """Подчинённые задачи проектных задач + факт-часы сотрудника за квартал.

    Один запрос на все дочерние Issue + один сгруппированный запрос факта.
    Возвращает {parent_issue_id: [child dict, ...]} (без пустых родителей).
    """
    from app.models import Issue

    ids = [i for i in issue_ids if i]
    if not ids:
        return {}
    rows = (
        db.query(Issue.id, Issue.key, Issue.summary, Issue.status, Issue.parent_id)
        .filter(Issue.parent_id.in_(ids))
        .all()
    )
    if not rows:
        return {}
    fact = _worklog_fact_map(
        db, [(employee_id, r.id) for r in rows], q_start, q_end
    )
    by_parent: Dict[str, List[dict]] = {}
    for r in rows:
        by_parent.setdefault(r.parent_id, []).append(
            {
                "key": r.key,
                "title": r.summary,
                "jira_url": _jira_url(r.key),
                "status": r.status,
                "fact_hours": round(fact.get((employee_id, r.id), 0.0), 1),
            }
        )
    for lst in by_parent.values():
        lst.sort(key=lambda c: (-c["fact_hours"], c["key"] or ""))
    return by_parent


def _worklog_span_map(
    db: Session,
    pairs: List[tuple[str, str]],
    q_start: date,
    q_end: date,
) -> Dict[tuple[str, str], tuple]:
    """Мин/макс дата ворклога по парам (employee_id, issue_id) за квартал."""
    if not pairs:
        return {}
    from app.models import Worklog

    emp_ids = {p[0] for p in pairs}
    issue_ids = {p[1] for p in pairs}
    start_dt = datetime.combine(q_start, time.min)
    end_dt = datetime.combine(q_end, time.max)
    rows = (
        db.query(
            Worklog.employee_id,
            Worklog.issue_id,
            func.min(Worklog.started_at).label("mn"),
            func.max(Worklog.started_at).label("mx"),
        )
        .filter(
            Worklog.employee_id.in_(emp_ids),
            Worklog.issue_id.in_(issue_ids),
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
        )
        .group_by(Worklog.employee_id, Worklog.issue_id)
        .all()
    )
    return {(r.employee_id, r.issue_id): (r.mn, r.mx) for r in rows}


def _merge_projects(projects: List[dict]) -> List[dict]:
    """Свернуть несколько отрезков одного проекта (одинаковый key) в одну строку.

    Часы суммируются, период растягивается на самый ранний старт и самый
    поздний финиш, % пересчитывается. Статус/название берутся из первого
    отрезка (у назначений одной задачи они совпадают). Строки без key
    (нераспознанные) остаются как есть — сворачивать их не по чему.
    """
    merged: Dict[str, dict] = {}
    order: List[str] = []
    extras: List[dict] = []
    for p in projects:
        key = p.get("key")
        if not key:
            extras.append(p)
            continue
        if key not in merged:
            merged[key] = dict(p)
            order.append(key)
            continue
        m = merged[key]
        m["norm_hours"] = round(m["norm_hours"] + p["norm_hours"], 1)
        m["fact_hours"] = round(m["fact_hours"] + p["fact_hours"], 1)
        if p["start_date"] and (not m["start_date"] or p["start_date"] < m["start_date"]):
            m["start_date"] = p["start_date"]
        if p["end_date"] and (not m["end_date"] or p["end_date"] > m["end_date"]):
            m["end_date"] = p["end_date"]
    for key in order:
        m = merged[key]
        m["pct"] = round(m["fact_hours"] / m["norm_hours"] * 100) if m["norm_hours"] > 0 else 0
    return [merged[k] for k in order] + extras


def _assignment_norm(a) -> float:
    """Плановые часы фазы: hours_allocated, иначе оценка роли на BacklogItem.

    hours_allocated часто пустой/0 — тогда берём per-role оценку из связанной
    инициативы (analyst/dev/qa/opo → estimate_*_hours). Если обоих нет — 0.0.
    """
    allocated = a.hours_allocated
    if allocated is not None and allocated > 0:
        return float(allocated)
    item = a.backlog_item
    if item is not None:
        field = _PHASE_ESTIMATE_FIELD.get(a.phase)
        if field is not None:
            est = getattr(item, field, None)
            if est is not None:
                return float(est)
    return 0.0


def _issue_fact_in_window(
    db: Session, employee_id: str, issue_id: str, start: date, end: date
) -> float:
    from app.models import Worklog

    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.max)
    total = (
        db.query(func.coalesce(func.sum(Worklog.hours), 0.0))
        .filter(
            Worklog.employee_id == employee_id,
            Worklog.issue_id == issue_id,
            Worklog.started_at >= start_dt,
            Worklog.started_at <= end_dt,
        )
        .scalar()
    )
    return float(total or 0.0)


# ──────────────────────────────────────────────────────────────────────────
# Адаптеры виджетов
# ──────────────────────────────────────────────────────────────────────────


def _adapter_my_tasks(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Проекты текущего сотрудника в свежем ресурсном плане квартала."""
    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return {"projects": []}
    q_start, q_end = _quarter_bounds(year, quarter)
    projects = _merge_projects(
        _assignment_projects(db, plan.id, desk.employee_id, q_start, q_end)
    )
    children = _project_children(
        db,
        desk.employee_id,
        [p.get("issue_id") for p in projects],
        q_start,
        q_end,
    )
    for p in projects:
        p["children"] = children.get(p.get("issue_id"), [])
    return {"projects": projects}


def _adapter_my_timeline(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Горизонтальная шкала проектов сотрудника по кварталу.

    Только назначения с обеими датами — иначе их некуда поставить на шкале.
    """
    q_start, q_end = _quarter_bounds(year, quarter)
    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    bars: List[dict] = []
    if plan is not None:
        rows = _assignment_projects(db, plan.id, desk.employee_id, q_start, q_end)
        dated = [p for p in rows if p["start_date"] and p["end_date"]]
        span = _worklog_span_map(
            db,
            [(desk.employee_id, p["issue_id"]) for p in dated if p.get("issue_id")],
            q_start,
            q_end,
        )
        for p in dated:
            mn_mx = span.get((desk.employee_id, p.get("issue_id")))
            fact_start = mn_mx[0].date().isoformat() if mn_mx and mn_mx[0] else None
            fact_end = mn_mx[1].date().isoformat() if mn_mx and mn_mx[1] else None
            bars.append(
                {
                    "key": p["key"],
                    "title": p["title"],
                    "start_date": p["start_date"],
                    "end_date": p["end_date"],
                    "status": p["status"],
                    "fact_start": fact_start,
                    "fact_end": fact_end,
                }
            )
    return {
        "quarter_start": q_start.isoformat(),
        "quarter_end": q_end.isoformat(),
        "bars": bars,
    }


def _employee_balance(db: Session, desk: WorkDesk):
    """EmployeeDetailResult с 1 января по сегодня для сотрудника стола.

    None, если сотрудника нет (инвариант FK не должен это допускать, но
    адаптеры баланса возвращают пустой результат вместо 500).
    """
    from app.services.hours_balance_service import HoursBalanceService

    today = date.today()
    from_ = date(today.year, 1, 1)
    try:
        return HoursBalanceService(db).compute_employee(
            desk.employee_id, from_, today, teams_filter=_desk_teams(desk) or None
        )
    except ValueError:
        return None


def _adapter_hours_balance(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Накопительный баланс часов сотрудника с начала года."""
    result = _employee_balance(db, desk)
    if result is None:
        return {"balance_hours": 0.0, "days": []}
    days = [
        {
            "date": d.day.isoformat(),
            "kind": d.kind,
            "delta": round(d.delta, 1),
        }
        for d in result.days
    ]
    return {"balance_hours": round(result.balance_hours, 1), "days": days}


def _adapter_category_breakdown(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Разворачиваемая иерархия сотрудника: Вид работ → Категория → Задача.

    Костяк — иерархический отчёт Аналитики (`get_hierarchical_report`),
    ограниченный сотрудником стола: даёт факт-часы и вложенные категории с
    задачами. Плановые часы видов работ накладываем из дашборда «Норма работ»
    (тот же расчёт плана, что на дашборде), сматчив по названию вида.
    """
    from app.services.analytics_service import AnalyticsService

    teams = _desk_teams(desk)
    svc = AnalyticsService(db)

    # План по видам работ (по названию) — идентичен дашборду.
    plan_by_label: Dict[str, float] = {}
    try:
        norm = svc.get_dashboard_norm_work(year=year, quarter=quarter, teams=teams or None)
        for role in norm.roles:
            for emp in role.employees:
                if emp.employee_id == desk.employee_id:
                    for wt in emp.work_types:
                        plan_by_label[wt.label] = wt.plan_hours
    except ValueError:
        pass

    # Факт + иерархия категорий/задач конкретного сотрудника.
    try:
        report = svc.get_hierarchical_report(
            year=year, quarter=quarter, teams=teams or None, employee_id=desk.employee_id
        )
    except ValueError:
        return {"work_types": []}

    emp_node = None
    for team_node in report.teams:
        for role_node in team_node.roles:
            for e in role_node.employees:
                if e.employee_id == desk.employee_id:
                    emp_node = e
                    break
    if emp_node is None:
        return {"work_types": []}

    work_types: List[dict] = []
    for wt in emp_node.work_types:
        plan = plan_by_label.get(wt.label)
        fact = round(wt.totals.fact_hours, 1)
        pct = round(fact / plan * 100) if plan else 0
        categories = [
            {
                "label": cat.label,
                "color": cat.color,
                "fact_hours": round(cat.totals.fact_hours, 1),
                "issues": [
                    {
                        "key": iss.key,
                        "title": iss.summary,
                        "jira_url": _jira_url(iss.key),
                        "status": iss.status,
                        "fact_hours": round(iss.totals.fact_hours, 1),
                    }
                    for iss in cat.issues
                ],
            }
            for cat in wt.categories
        ]
        work_types.append(
            {
                "label": wt.label,
                "plan_hours": round(plan, 1) if plan else 0.0,
                "fact_hours": fact,
                "pct": pct,
                "categories": categories,
            }
        )
    return {"work_types": work_types}


def _adapter_team_absences(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Отсутствия команд стола за квартал + строки-сотрудники для сетки-теплокарты."""
    from app.models import Absence, Employee
    from app.models.absence_reason import AbsenceReason
    from app.models.employee_team import EmployeeTeam

    teams = _desk_teams(desk)
    if not teams:
        return {"employees": [], "absences": [], "year": year, "quarter": quarter}

    q_start, q_end = _quarter_bounds(year, quarter)

    # Все сотрудники команд — строки сетки даже без отсутствий.
    emp_rows = (
        db.query(Employee.id, Employee.display_name)
        .join(EmployeeTeam, EmployeeTeam.employee_id == Employee.id)
        .filter(EmployeeTeam.team.in_(teams))
        .distinct()
        .order_by(Employee.display_name)
        .all()
    )
    employees = [{"id": r.id, "display_name": r.display_name} for r in emp_rows]

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
            "employee_id": emp.id,
            "employee_name": emp.display_name,
            "start_date": ab.start_date.isoformat(),
            "end_date": ab.end_date.isoformat(),
            "reason_label": reason.label,
            "reason_color": reason.color,
        }
        for ab, reason, emp in rows
    ]
    return {
        "employees": employees,
        "absences": absences,
        "year": year,
        "quarter": quarter,
    }


def _adapter_team_availability(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Занятость команды: проекты каждого коллеги в свежем плане квартала."""
    from app.models import Employee, ResourcePlanAssignment

    teams = _desk_teams(desk)
    q_start, q_end = _quarter_bounds(year, quarter)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return {
            "members": [],
            "quarter_start": q_start.isoformat(),
            "quarter_end": q_end.isoformat(),
        }

    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.employee_id.is_not(None),
            )
            .order_by(ResourcePlanAssignment.start_date)
        )
        .scalars()
        .all()
    )

    # Все пары (employee, issue) — один сгруппированный квартальный факт.
    pairs: List[tuple[str, str]] = []
    assignment_issue: Dict[str, object] = {}
    for a in rows:
        item = a.backlog_item
        issue = item.issue if item is not None else None
        assignment_issue[a.id] = issue
        if issue is not None and a.employee_id:
            pairs.append((a.employee_id, issue.id))
    quarter_fact = _worklog_fact_map(db, pairs, q_start, q_end)

    # Имена и роли сотрудников плана.
    emp_ids = {a.employee_id for a in rows if a.employee_id}
    names: Dict[str, str] = {}
    dev_ids: set[str] = set()
    if emp_ids:
        for eid, dname, role in (
            db.query(Employee.id, Employee.display_name, Employee.role)
            .filter(Employee.id.in_(emp_ids))
            .all()
        ):
            names[eid] = dname
            if (role or "").lower() in ("dev", "developer"):
                dev_ids.add(eid)

    # Исключаем самого сотрудника стола и разработчиков.
    excluded = dev_ids | {desk.employee_id}

    by_emp: Dict[str, dict] = {}
    for a in rows:
        eid = a.employee_id
        if eid in excluded:
            continue
        issue = assignment_issue.get(a.id)
        key = getattr(issue, "key", None)
        norm = _assignment_norm(a)
        if issue is None:
            fact = 0.0
        elif a.start_date and a.end_date:
            fact = _issue_fact_in_window(db, eid, issue.id, a.start_date, a.end_date)
        else:
            fact = quarter_fact.get((eid, issue.id), 0.0)
        pct = round(fact / norm * 100) if norm > 0 else 0

        entry = by_emp.setdefault(
            eid,
            {"id": eid, "display_name": names.get(eid, eid), "projects": []},
        )
        entry["projects"].append(
            {
                "key": key,
                "title": a.backlog_item.title if a.backlog_item is not None else None,
                "jira_url": _jira_url(key),
                "status": getattr(issue, "status", None),
                "start_date": a.start_date.isoformat() if a.start_date else None,
                "end_date": a.end_date.isoformat() if a.end_date else None,
                "norm_hours": round(norm, 1),
                "fact_hours": round(fact, 1),
                "pct": pct,
            }
        )
    for entry in by_emp.values():
        entry["projects"] = _merge_projects(entry["projects"])
    return {
        "members": list(by_emp.values()),
        "quarter_start": q_start.isoformat(),
        "quarter_end": q_end.isoformat(),
    }


def _adapter_production_calendar(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Производственный календарь всего квартала + счётчики рабочих дней."""
    from app.services.production_calendar_service import ProductionCalendarService

    svc = ProductionCalendarService(db)
    q_start, q_end = _quarter_bounds(year, quarter)
    hours_map = svc.hours_in_range_map(q_start, q_end)
    workdays_map = svc.workdays_in_range_map(q_start, q_end)

    # Точные kind'ы из БД (sparse — только аномалии/синхронизированные дни).
    from app.models import ProductionCalendarDay

    kind_rows = (
        db.query(ProductionCalendarDay.date, ProductionCalendarDay.kind)
        .filter(
            ProductionCalendarDay.date >= q_start,
            ProductionCalendarDay.date <= q_end,
        )
        .all()
    )
    kind_map = {r.date: r.kind for r in kind_rows}

    today = date.today()
    cur_month = today.month if today.year == year else None

    quarter_workdays = 0
    month_workdays = 0
    quarter_work_hours = 0.0
    month_work_hours = 0.0
    days: List[dict] = []
    cur = q_start
    while cur <= q_end:
        is_wd = workdays_map.get(cur, cur.weekday() < 5)
        h = hours_map.get(cur)
        if h is None:
            h = 8.0 if cur.weekday() < 5 else 0.0
        kind = kind_map.get(cur)
        if kind is None:
            kind = "workday" if cur.weekday() < 5 else "weekend"
        quarter_work_hours += float(h)
        if is_wd:
            quarter_workdays += 1
            if cur_month is not None and cur.month == cur_month:
                month_workdays += 1
        if cur_month is not None and cur.month == cur_month:
            month_work_hours += float(h)
        days.append({"date": cur.isoformat(), "kind": kind, "hours": float(h)})
        cur += timedelta(days=1)
    return {
        "quarter_workdays": quarter_workdays,
        "month_workdays": month_workdays,
        "quarter_work_hours": round(quarter_work_hours, 1),
        "month_work_hours": round(month_work_hours, 1),
        "days": days,
    }


def _adapter_awaiting_reaction(
    db: Session, desk: WorkDesk, year: int, quarter: int
) -> dict:
    """Ждут реакции: задачи, где сотрудник — исполнитель, не завершены,
    а последний комментарий оставил кто-то другой (мяч на стороне сотрудника).

    Сигнал исполнителя — только строка Issue.assignee_display_name (FK нет),
    сравниваем с Employee.display_name без учёта регистра. Задачи без
    комментариев исключаются — отвечать не на что.
    """
    from app.models import Comment, Employee, Issue

    emp = db.get(Employee, desk.employee_id)
    if emp is None or not emp.display_name:
        return {"items": []}

    # SQLite lower() не трогает кириллицу — сравнение без учёта регистра делаем
    # в Python (casefold). В БД отсекаем только завершённые и без исполнителя.
    target = emp.display_name.strip().casefold()
    rows = (
        db.query(Issue.id, Issue.key, Issue.summary, Issue.status, Issue.assignee_display_name)
        .filter(
            Issue.assignee_display_name.is_not(None),
            func.coalesce(Issue.status_category, "") != "done",
        )
        .all()
    )
    candidate_issues = [
        r for r in rows if (r.assignee_display_name or "").strip().casefold() == target
    ]
    if not candidate_issues:
        return {"items": []}

    issue_ids = [r.id for r in candidate_issues]
    meta = {r.id: (r.key, r.summary, r.status) for r in candidate_issues}

    # Последний комментарий на задачу — сгруппированный max(jira_created_at).
    latest_sub = (
        db.query(
            Comment.issue_id.label("issue_id"),
            func.max(Comment.jira_created_at).label("max_created"),
        )
        .filter(
            Comment.issue_id.in_(issue_ids),
            Comment.jira_created_at.is_not(None),
        )
        .group_by(Comment.issue_id)
        .subquery()
    )
    latest_comments = (
        db.query(Comment)
        .join(
            latest_sub,
            (Comment.issue_id == latest_sub.c.issue_id)
            & (Comment.jira_created_at == latest_sub.c.max_created),
        )
        .all()
    )

    # Имена авторов последних комментариев.
    author_ids = {c.author_id for c in latest_comments if c.author_id}
    author_names: Dict[str, str] = {}
    if author_ids:
        for eid, dname in (
            db.query(Employee.id, Employee.display_name)
            .filter(Employee.id.in_(author_ids))
            .all()
        ):
            author_names[eid] = dname

    items: List[dict] = []
    seen: set[str] = set()
    for c in latest_comments:
        if c.issue_id in seen:
            continue
        # Последний комментарий от самого сотрудника → мяч не на его стороне.
        if c.author_id == desk.employee_id:
            continue
        seen.add(c.issue_id)
        key, summary, status = meta.get(c.issue_id, (None, None, None))
        items.append(
            {
                "key": key,
                "title": summary,
                "status": status,
                "last_comment_at": c.jira_created_at.isoformat()
                if c.jira_created_at
                else None,
                "last_comment_author": author_names.get(c.author_id) if c.author_id else None,
            }
        )

    items.sort(key=lambda x: x["last_comment_at"] or "", reverse=True)
    return {"items": items[:30]}


# Реестр: ключ → адаптер.
_REGISTRY: Dict[str, Callable[[Session, WorkDesk, int, int], dict]] = {
    "my_tasks": _adapter_my_tasks,
    "my_timeline": _adapter_my_timeline,
    "hours_balance": _adapter_hours_balance,
    "category_breakdown": _adapter_category_breakdown,
    "team_absences": _adapter_team_absences,
    "team_availability": _adapter_team_availability,
    "production_calendar": _adapter_production_calendar,
    "awaiting_reaction": _adapter_awaiting_reaction,
}


def dispatch(db: Session, desk: WorkDesk, key: str, year: int, quarter: int) -> dict:
    """Вычислить данные одного виджета. ValueError если ключ неизвестен."""
    if key not in WIDGET_KEYS:
        raise ValueError(f"Unknown widget key: {key}")
    adapter = _REGISTRY[key]
    return adapter(db, desk, year, quarter)


# ──────────────────────────────────────────────────────────────────────────
# Hero-сводка для шапки стола (независима от включённых виджетов)
# ──────────────────────────────────────────────────────────────────────────


def _remaining_workdays_month(db: Session, today: date) -> int:
    """Рабочих дней с сегодня (включительно) до конца текущего месяца."""
    from app.services.production_calendar_service import ProductionCalendarService

    last_day = date(today.year, today.month, _cal.monthrange(today.year, today.month)[1])
    if last_day < today:
        return 0
    workdays_map = ProductionCalendarService(db).workdays_in_range_map(today, last_day)
    count = 0
    cur = today
    while cur <= last_day:
        if workdays_map.get(cur, cur.weekday() < 5):
            count += 1
        cur += timedelta(days=1)
    return count


def _projects_in_progress(db: Session, desk: WorkDesk, year: int, quarter: int) -> int:
    """Проекты сотрудника в работе на свежем плане квартала.

    Считаем уникальные задачи назначений сотрудника, чья связанная Issue
    не завершена (status_category != 'done'). Без плана / без задач → 0.
    """
    from app.models import ResourcePlanAssignment

    teams = _desk_teams(desk)
    plan = _find_recent_plan(db, teams, year, quarter)
    if plan is None:
        return 0
    rows = (
        db.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.employee_id == desk.employee_id,
            )
        )
        .scalars()
        .all()
    )
    in_progress: set[str] = set()
    for a in rows:
        item = a.backlog_item
        issue = item.issue if item is not None else None
        if issue is None:
            continue
        if (getattr(issue, "status_category", None) or "").lower() != "done":
            in_progress.add(issue.id)
    return len(in_progress)


def desk_summary(db: Session, desk: WorkDesk, year: int, quarter: int) -> dict:
    """Три hero-числа шапки стола. Защищён от 500 — при ошибке часть → 0.

    - overtime_hours: накопительный баланс факт−норма с 1 января
      (тот же путь, что у виджета hours_balance).
    - remaining_workdays_month: рабочих дней до конца текущего месяца включительно.
    - projects_in_progress: незавершённые проекты сотрудника на свежем плане.
    """
    today = date.today()

    balance = _employee_balance(db, desk)
    overtime_hours = round(balance.balance_hours, 1) if balance is not None else 0.0

    return {
        "overtime_hours": overtime_hours,
        "remaining_workdays_month": _remaining_workdays_month(db, today),
        "projects_in_progress": _projects_in_progress(db, desk, year, quarter),
    }
