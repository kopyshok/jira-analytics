"""Занятость сотрудников в планах других команд.

Опорный план команды на квартал — тот, по которому остальные команды видят,
когда её люди заняты: основной (иначе «Готово», иначе самый свежий) план
утверждённого сценария; нет утверждённого — план самого свежего черновика
с признаком «предварительно». Копии-форки не участвуют.

Все функции — чистое чтение, без commit.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import BacklogItem, PlanningScenario, ResourcePlan, ResourcePlanAssignment
from app.services import team_membership as tm
from app.services.plan_common import _plan_sort_key, _quarter_variants


@dataclass(frozen=True)
class ReferencePlan:
    """Опорный план команды на квартал."""

    plan_id: str
    team: str
    provisional: bool


def quarter_num(value) -> Optional[int]:
    """«Q3» / «3» / 3 → 3; мусор → None."""
    try:
        q = int(str(value or "").strip().upper().lstrip("Q"))
    except ValueError:
        return None
    return q if 1 <= q <= 4 else None


def _ref_key(plan: ResourcePlan) -> tuple:
    """Порядок выбора внутри сценариев: основной → «Готово» → свежесть."""
    return (bool(plan.is_baseline), plan.status == "ready", _plan_sort_key(plan))


def reference_plans(
    db: Session,
    year: int,
    quarter: int,
    exclude_team: Optional[str] = None,
) -> Dict[str, ReferencePlan]:
    """Опорные планы всех команд квартала: {команда: ReferencePlan}.

    Один запрос. ``exclude_team`` — команда, чей собственный план не должен
    считаться «чужой» занятостью.
    """
    rows = db.execute(
        select(ResourcePlan, PlanningScenario)
        .join(PlanningScenario, PlanningScenario.id == ResourcePlan.scenario_id)
        .where(
            ResourcePlan.year == year,
            ResourcePlan.quarter.in_(_quarter_variants(quarter)),
            ResourcePlan.parent_plan_id.is_(None),
            ResourcePlan.team.is_not(None),
            PlanningScenario.status.in_(("approved", "draft")),
        )
    ).all()

    approved: Dict[str, list] = defaultdict(list)
    drafts: Dict[str, list] = defaultdict(list)
    for plan, sc in rows:
        if exclude_team is not None and plan.team == exclude_team:
            continue
        bucket = approved if sc.status == "approved" else drafts
        bucket[plan.team].append((plan, sc))

    out: Dict[str, ReferencePlan] = {}
    for team in set(approved) | set(drafts):
        if approved.get(team):
            best = max((p for p, _ in approved[team]), key=_ref_key)
            out[team] = ReferencePlan(best.id, team, False)
            continue
        fresh_sc = max(
            (sc for _, sc in drafts[team]),
            key=lambda s: (s.updated_at or s.created_at or datetime.min, s.id),
        )
        best = max(
            (p for p, sc in drafts[team] if sc.id == fresh_sc.id), key=_ref_key
        )
        out[team] = ReferencePlan(best.id, team, True)
    return out


@dataclass
class ExternalBooking:
    """Фаза сотрудника в опорном плане другой команды."""

    assignment_id: str
    employee_id: str
    team: str
    issue_key: Optional[str]
    title: str
    phase: str
    start: date
    end: date
    daily_hours: Dict[date, float]
    provisional: bool


def _assignment_daily(a: ResourcePlanAssignment) -> Dict[date, float]:
    """Часы фазы по дням: раскладка планировщика, иначе поровну по будням."""
    if a.daily_hours_json:
        try:
            raw = json.loads(a.daily_hours_json)
            daily = {
                date.fromisoformat(k): float(v) for k, v in raw.items() if float(v) > 0
            }
        except (ValueError, TypeError, AttributeError):
            daily = {}
        if daily:
            return daily
    if not a.start_date or not a.end_date or not a.hours_allocated:
        return {}
    days: List[date] = []
    d = a.start_date
    while d <= a.end_date:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    if not days:
        days = [a.start_date]
    per = float(a.hours_allocated) / len(days)
    return {d: per for d in days}


def external_bookings(
    db: Session,
    *,
    team: Optional[str],
    year: Optional[int],
    quarter: Optional[int],
    employee_ids: Iterable[Optional[str]],
    start: date,
    end: date,
) -> List[ExternalBooking]:
    """Брони сотрудников в опорных планах квартала всех команд, кроме ``team``.

    ``team=None`` — берутся опорные планы всех команд (загрузка за квартал).
    Два запроса на любой объём: опорные планы + их назначения.
    """
    ids = [i for i in dict.fromkeys(employee_ids) if i]
    if not ids or not year or not quarter:
        return []
    refs = reference_plans(db, year, quarter, exclude_team=team)
    if not refs:
        return []
    by_plan = {r.plan_id: r for r in refs.values()}
    rows = (
        db.execute(
            select(ResourcePlanAssignment)
            .options(
                joinedload(ResourcePlanAssignment.backlog_item).joinedload(
                    BacklogItem.issue
                )
            )
            .where(
                ResourcePlanAssignment.plan_id.in_(list(by_plan)),
                ResourcePlanAssignment.employee_id.in_(ids),
                ResourcePlanAssignment.start_date <= end,
                ResourcePlanAssignment.end_date >= start,
            )
        )
        .scalars()
        .unique()
        .all()
    )
    out: List[ExternalBooking] = []
    for a in rows:
        if not a.employee_id or a.start_date is None or a.end_date is None:
            continue
        daily = {d: h for d, h in _assignment_daily(a).items() if start <= d <= end}
        if not daily:
            continue
        ref = by_plan[a.plan_id]
        bi = a.backlog_item
        out.append(
            ExternalBooking(
                assignment_id=a.id,
                employee_id=a.employee_id,
                team=ref.team,
                issue_key=bi.issue.key if bi is not None and bi.issue is not None else None,
                title=bi.title if bi is not None else "",
                phase=a.phase,
                start=a.start_date,
                end=a.end_date,
                daily_hours=daily,
                provisional=ref.provisional,
            )
        )
    out.sort(key=lambda b: (b.employee_id, b.start, b.issue_key or "", b.phase))
    return out


def daily_totals(bookings: Iterable[ExternalBooking]) -> Dict[str, Dict[date, float]]:
    """{сотрудник: {день: часы во всех бронях}}."""
    acc: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for b in bookings:
        for d, h in b.daily_hours.items():
            acc[b.employee_id][d] += h
    return {eid: dict(days) for eid, days in acc.items()}


def subtract_occupancy(
    avail: Dict[str, Dict[date, float]],
    occupied: Dict[str, Dict[date, float]],
) -> Dict[str, Dict[date, float]]:
    """Доступность минус внешняя занятость, не ниже нуля. Новый словарь."""
    return {
        eid: {
            d: max(0.0, h - occupied.get(eid, {}).get(d, 0.0))
            for d, h in days.items()
        }
        for eid, days in avail.items()
    }


def overlap_days(
    own: Dict[date, float],
    external: Dict[date, float],
    capacity: Dict[date, float],
) -> List[date]:
    """Дни, где часы этого плана + брони других команд больше ёмкости дня.

    Берутся только дни, в которые этот план сам ставит работу (иначе
    пересечение — не его забота) и которые есть в ``capacity``.
    """
    return sorted(
        d
        for d, h in external.items()
        if h > 0
        and d in capacity
        and own.get(d, 0.0) > 0
        and own.get(d, 0.0) + h > capacity[d] + 0.01
    )


def borrowed_ids(
    db: Session,
    team: Optional[str],
    start: date,
    end: date,
    employee_ids: Iterable[Optional[str]],
) -> set[str]:
    """Кто из перечисленных не состоял в ``team`` ни дня периода."""
    if not team:
        return set()
    members = set(tm.member_intervals(db, [team], start, end))
    return {e for e in employee_ids if e and e not in members}
