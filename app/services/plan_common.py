"""Общие расчёты плана: используются и рабочими столами, и разделом «Проекты».

Столы дают персональный срез (доля одного сотрудника), «Проекты» — проектный
(все исполнители). Формулы плана/факта одни и те же, поэтому живут здесь.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

QUARTER_MONTHS: Dict[int, tuple[int, int, int]] = {
    1: (1, 2, 3),
    2: (4, 5, 6),
    3: (7, 8, 9),
    4: (10, 11, 12),
}

JIRA_BROWSE = "https://itgri.atlassian.net/browse/"

# Все фазы плана.
ROLES: tuple[str, ...] = ("analyst", "dev", "qa", "opo")

# Фазы, для которых рисуем плитку/кольцо. ОПЭ отдельно не показываем — его план
# раскидывается по Анализу и Разработке (см. role_breakdown).
DISPLAY_ROLES: tuple[str, ...] = ("analyst", "dev", "qa")

# Фаза назначения → поле плановой оценки на BacklogItem.
PHASE_ESTIMATE_FIELD: Dict[str, str] = {
    "analyst": "estimate_analyst_hours",
    "dev": "estimate_dev_hours",
    "qa": "estimate_qa_hours",
    "opo": "estimate_opo_hours",
}

# Фаза назначения → человекочитаемое название.
PHASE_LABEL: Dict[str, str] = {
    "analyst": "Анализ",
    "cons": "Консультация",
    "dev": "Разработка",
    "qa": "Тестирование",
    "opo": "ОПЭ",
}


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    months = QUARTER_MONTHS[quarter]
    start = date(year, months[0], 1)
    last_month = months[-1]
    end = date(year, last_month, _cal.monthrange(year, last_month)[1])
    return start, end


def jira_url(key: Optional[str]) -> Optional[str]:
    return f"{JIRA_BROWSE}{key}" if key else None


def find_recent_plan(db: Session, teams: List[str], year: int, quarter: int):
    """Самый свежий ResourcePlan команды за квартал, либо None."""
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


def plan_ids_for_issues(db: Session, issue_ids: Sequence[str]) -> List[str]:
    """Планы, где есть назначения этих задач — по свежайшему на каждый квартал.

    Проект может идти два-три квартала, назначения лежат в разных ResourcePlan.
    Форки и baseline-копии одного квартала удвоили бы часы, поэтому на каждую
    тройку (команда, год, квартал) оставляем только самый свежий план.
    """
    from app.models import BacklogItem, ResourcePlan, ResourcePlanAssignment

    ids = [i for i in dict.fromkeys(issue_ids) if i]
    if not ids:
        return []
    raw_plan_ids = (
        db.execute(
            select(ResourcePlanAssignment.plan_id)
            .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
            .where(BacklogItem.issue_id.in_(ids))
            .distinct()
        )
        .scalars()
        .all()
    )
    if not raw_plan_ids:
        return []
    plans = (
        db.execute(select(ResourcePlan).where(ResourcePlan.id.in_(raw_plan_ids)))
        .scalars()
        .all()
    )
    best: Dict[tuple, object] = {}
    for p in plans:
        # Квартал в БД встречается как "3", "Q3", "q3" — нормализуем.
        q = (p.quarter or "").lower().lstrip("q")
        bucket = (p.team, p.year, q)
        cur = best.get(bucket)
        if cur is None or _plan_sort_key(p) > _plan_sort_key(cur):
            best[bucket] = p
    return [p.id for p in best.values()]


def _plan_sort_key(p) -> tuple:
    """Свежесть плана: сначала computed_at, затем created_at. None — самый старый."""
    return (
        p.computed_at or datetime.min,
        p.created_at or datetime.min,
    )


def subtree_ids(db: Session, root_ids: Sequence[str]) -> Dict[str, set]:
    """Для каждой задачи-корня — множество id её поддерева (корень + потомки).

    Списания часто висят на подзадачах, а не на задаче-инициативе. BFS по
    Issue.parent_id уровнями (несколько запросов, ограничено глубиной дерева).
    """
    from app.models import Issue

    roots = [r for r in dict.fromkeys(root_ids) if r]
    result: Dict[str, set] = {r: {r} for r in roots}
    if not roots:
        return result
    parent_root: Dict[str, str] = {r: r for r in roots}
    current = list(roots)
    while current:
        rows = (
            db.query(Issue.id, Issue.parent_id)
            .filter(Issue.parent_id.in_(current))
            .all()
        )
        nxt: List[str] = []
        for cid, pid in rows:
            root = parent_root.get(pid)
            if root is None or cid in result[root]:
                continue
            result[root].add(cid)
            parent_root[cid] = root
            nxt.append(cid)
        current = nxt
    return result


def team_member_ids(db: Session, teams: Sequence[str]) -> set[str]:
    """ID сотрудников указанных команд + QA (общий ресурс компании)."""
    from app.models import Employee
    from app.models.employee_team import EmployeeTeam

    ids: set[str] = set()
    if teams:
        rows = db.query(EmployeeTeam.employee_id).filter(EmployeeTeam.team.in_(list(teams))).all()
        ids = {r[0] for r in rows}
    qa_rows = db.query(Employee.id).filter(Employee.role == "qa").all()
    ids |= {r[0] for r in qa_rows}
    return ids


def assignment_norm(a) -> float:
    """Плановые часы фазы: hours_allocated, иначе оценка роли на BacklogItem."""
    allocated = a.hours_allocated
    if allocated is not None and allocated > 0:
        return float(allocated)
    item = a.backlog_item
    if item is not None:
        field = PHASE_ESTIMATE_FIELD.get(a.phase)
        if field is not None:
            est = getattr(item, field, None)
            if est is not None:
                return float(est)
    return 0.0


def role_breakdown(
    db: Session,
    plan_ids: Sequence[str],
    root_ids: Sequence[str],
    subtree: Dict[str, set],
    fact_until: date,
    team_ids: set[str],
) -> Dict[str, dict]:
    """План/факт по видам работ для каждой задачи-корня.

    План — плановые часы всех фаз проекта во всех переданных планах.
    Факт — накопительно по всему поддереву до ``fact_until``, разнесённый по
    роли автора ворклога; роль РП засчитывается в Анализ.

    Часы авторов вне команды и без плитки-роли идут в «прочее» (``info``) —
    они не входят в план/факт, показываются информационно.

    Возвращает {root_issue_id: {"plan": {role: ч}, "fact": {role: ч}, "info": ч}}.
    """
    from app.models import BacklogItem, Employee, ResourcePlanAssignment, Worklog

    ids = [i for i in root_ids if i]
    out: Dict[str, dict] = {
        i: {"plan": {r: 0.0 for r in ROLES}, "fact": {r: 0.0 for r in ROLES}, "info": 0.0}
        for i in ids
    }
    if not ids:
        return out

    ratios: Dict[str, float] = {}
    if plan_ids:
        arows = (
            db.query(
                ResourcePlanAssignment,
                BacklogItem.issue_id,
                BacklogItem.opo_analyst_ratio,
            )
            .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
            .filter(
                ResourcePlanAssignment.plan_id.in_(list(plan_ids)),
                BacklogItem.issue_id.in_(ids),
            )
            .all()
        )
        for a, issue_id, opo_ratio in arows:
            if a.phase in ROLES and issue_id in out:
                out[issue_id]["plan"][a.phase] += assignment_norm(a)
                ratios[issue_id] = 0.5 if opo_ratio is None else float(opo_ratio)

    issue_to_root: Dict[str, str] = {}
    for root, members in subtree.items():
        for iid in members:
            issue_to_root[iid] = root
    all_ids = list(issue_to_root.keys())
    if all_ids:
        end_dt = datetime.combine(fact_until, time.max)
        rows = (
            db.query(
                Worklog.issue_id,
                Worklog.employee_id,
                Employee.role,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
            )
            .join(Employee, Employee.id == Worklog.employee_id)
            .filter(
                Worklog.issue_id.in_(all_ids),
                Worklog.started_at <= end_dt,
            )
            .group_by(Worklog.issue_id, Worklog.employee_id, Employee.role)
            .all()
        )
        for issue_id, emp_id, role, hours in rows:
            root = issue_to_root.get(issue_id)
            if root not in out:
                continue
            h = float(hours or 0.0)
            r = (role or "").lower()
            if r == "rp":  # РП засчитываем в Анализ
                r = "analyst"
            if emp_id in team_ids and r in ROLES:
                out[root]["fact"][r] += h
            else:
                out[root]["info"] += h

    # ОПЭ нельзя зафиксировать по факту отдельно — план ОПЭ распределяем на
    # Анализ/Разработку по коэффициенту деления, плитку ОПЭ убираем.
    for iid, bd in out.items():
        ratio = ratios.get(iid, 0.5)
        for kind in ("plan", "fact"):
            opo = bd[kind].pop("opo", 0.0)
            bd[kind]["analyst"] += opo * ratio
            bd[kind]["dev"] += opo * (1.0 - ratio)
    return out
