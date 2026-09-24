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

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    BacklogItem,
    Employee,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.services import team_membership as tm
from app.services.plan_common import _plan_sort_key, _quarter_variants, quarter_bounds


@dataclass(frozen=True)
class ReferencePlan:
    """Опорный план команды на квартал."""

    plan_id: str
    team: str
    provisional: bool
    # Когда план последний раз считался — для признака устаревания чужих планов.
    computed_at: Optional[datetime] = None


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
            out[team] = ReferencePlan(best.id, team, False, best.computed_at)
            continue
        fresh_sc = max(
            (sc for _, sc in drafts[team]),
            key=lambda s: (s.updated_at or s.created_at or datetime.min, s.id),
        )
        best = max(
            (p for p, sc in drafts[team] if sc.id == fresh_sc.id), key=_ref_key
        )
        out[team] = ReferencePlan(best.id, team, True, best.computed_at)
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
    # Бронь-привлечение: в команде брони человек не состоял ни дня квартала
    # её плана — команда взяла его к себе.
    is_borrowing: bool = False
    # Когда бронь последний раз менялась: пересчёт опорного плана или правка строки.
    changed_at: Optional[datetime] = None


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


def _member_of(
    periods: Iterable[tuple[str, Optional[date], Optional[date], bool]],
    team: str,
    start: date,
    end: date,
) -> bool:
    """Состоял ли сотрудник в ``team`` хоть день отрезка.

    ``periods`` — его периоды участия из ``tm.membership_rows``:
    ``(команда, joined_at, left_at, основная)``, ``left_at`` — первый день вне команды.
    """
    return any(
        t == team
        and (joined is None or joined <= end)
        and (left is None or left > start)
        for t, joined, left, _primary in periods
    )


def _in_plan_scenario(stmt: Select) -> Select:
    """Только строки задач, которые всё ещё включены в сценарий своего плана.

    Задача, убранная из сценария или выключенная в нём, никого не занимает,
    даже если её фаза закреплена и план ещё не пересчитан.
    """
    return stmt.join(ResourcePlan, ResourcePlan.id == ResourcePlanAssignment.plan_id).join(
        ScenarioAllocation,
        and_(
            ScenarioAllocation.scenario_id == ResourcePlan.scenario_id,
            ScenarioAllocation.backlog_item_id == ResourcePlanAssignment.backlog_item_id,
            ScenarioAllocation.included_flag == True,  # noqa: E712
        ),
    )


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
    Кроме планов квартала — опорные планы прошлого квартала: их фазы выползают
    в этот квартал на месяц запаса и тоже занимают человека. Хвост задачи,
    которую команда перенесла в свой план этого квартала, не считается:
    там она уже занимает человека. Окно ``start`` — ``end`` отсекает всё,
    что в него не попадает. Строки задач, которых уже нет в сценарии плана,
    не считаются нигде.
    У каждой брони — ``is_borrowing`` (человек не состоял в команде брони ни
    дня квартала её плана: команда его привлекла) и ``changed_at`` (когда
    бронь последний раз менялась: пересчёт опорного плана или правка строки).
    Пять запросов на любой объём: опорные планы двух кварталов, задачи
    планов квартала, назначения и периоды участия их людей.
    """
    ids = [i for i in dict.fromkeys(employee_ids) if i]
    if not ids or not year or not quarter:
        return []
    prev_year, prev_quarter = (year, quarter - 1) if quarter > 1 else (year - 1, 4)
    prev_refs = reference_plans(db, prev_year, prev_quarter, exclude_team=team)
    cur_refs = reference_plans(db, year, quarter, exclude_team=team)
    by_plan = {r.plan_id: r for r in (*prev_refs.values(), *cur_refs.values())}
    if not by_plan:
        return []
    prev_ids = {r.plan_id for r in prev_refs.values()}
    # (команда, задача) из планов квартала — их хвосты прошлого квартала лишние.
    carried: set[tuple[str, str]] = set()
    if prev_ids and cur_refs:
        team_of = {r.plan_id: r.team for r in cur_refs.values()}
        carried = {
            (team_of[plan_id], item_id)
            for plan_id, item_id in db.execute(
                _in_plan_scenario(
                    select(
                        ResourcePlanAssignment.plan_id,
                        ResourcePlanAssignment.backlog_item_id,
                    )
                )
                .where(ResourcePlanAssignment.plan_id.in_(list(team_of)))
                .distinct()
            ).all()
        }
    rows = (
        db.execute(
            _in_plan_scenario(select(ResourcePlanAssignment))
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
    # Состав команды брони сверяется с кварталом её опорного плана: хвост
    # прошлого квартала — с прошлым кварталом.
    membership = tm.membership_rows(
        db, list({a.employee_id for a in rows if a.employee_id})
    )
    cur_bounds = quarter_bounds(year, quarter)
    prev_bounds = quarter_bounds(prev_year, prev_quarter)
    out: List[ExternalBooking] = []
    for a in rows:
        if not a.employee_id or a.start_date is None or a.end_date is None:
            continue
        ref = by_plan[a.plan_id]
        if a.plan_id in prev_ids and (ref.team, a.backlog_item_id) in carried:
            continue
        daily = {d: h for d, h in _assignment_daily(a).items() if start <= d <= end}
        if not daily:
            continue
        lo, hi = prev_bounds if a.plan_id in prev_ids else cur_bounds
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
                is_borrowing=not _member_of(
                    membership.get(a.employee_id, ()), ref.team, lo, hi
                ),
                changed_at=max(
                    (t for t in (ref.computed_at, a.updated_at) if t is not None),
                    default=None,
                ),
            )
        )
    out.sort(
        key=lambda b: (
            b.employee_id, b.start, b.issue_key or "", b.phase, b.assignment_id
        )
    )
    return out


def daily_totals(bookings: Iterable[ExternalBooking]) -> Dict[str, Dict[date, float]]:
    """{сотрудник: {день: часы во всех бронях}}."""
    acc: Dict[str, Dict[date, float]] = defaultdict(lambda: defaultdict(float))
    for b in bookings:
        for d, h in b.daily_hours.items():
            acc[b.employee_id][d] += h
    return {eid: dict(days) for eid, days in acc.items()}


def subtractable(
    bookings: Iterable[ExternalBooking], borrowed: set
) -> List[ExternalBooking]:
    """Брони, которые вычитаются из доступности плана: сначала домашняя команда.

    Привлечённому в план (``borrowed``) — все брони других команд. Своему
    сотруднику — только брони команд, где он тоже состоит (общий сотрудник).
    Бронь-привлечение своего (команда взяла его к себе, не имея в составе)
    доступность не уменьшает — подстраивается привлекающая команда.
    """
    return [b for b in bookings if b.employee_id in borrowed or not b.is_borrowing]


def stale_teams(
    bookings: Iterable[ExternalBooking], computed_at: Optional[datetime]
) -> List[str]:
    """Команды, чьи брони изменились после расчёта плана, по алфавиту.

    План ни разу не считался — сравнивать не с чем, список пуст.
    """
    if computed_at is None:
        return []
    return sorted(
        {b.team for b in bookings if b.changed_at is not None and b.changed_at > computed_at}
    )


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


def quarter_load_pct(
    db: Session,
    year: int,
    quarter: int,
    employees: List[Employee],
) -> Dict[str, float]:
    """Загрузка за квартал по всем опорным планам, % от «календарь − отсутствия».

    Знаменатель — доступность планировщика: часы производственного календаря
    (6 ч только для будней, которых в календаре нет), минус отсутствия.
    Числитель — брони опорных планов этого квартала и хвосты прошлого, вошедшие
    в квартал. Запросов — константа на любой объём: опорные планы, их
    назначения, календарь, отсутствия.
    """
    if not employees:
        return {}
    # Сервис планировщика сам импортирует этот модуль — отсюда только лениво.
    from app.services.resource_planning_service import ResourcePlanningService

    start, end = quarter_bounds(year, quarter)
    booked = daily_totals(
        external_bookings(
            db,
            team=None,
            year=year,
            quarter=quarter,
            employee_ids=[e.id for e in employees],
            start=start,
            end=end,
        )
    )
    avail = ResourcePlanningService(db).build_availability(employees, start, end, [])
    out: Dict[str, float] = {}
    for e in employees:
        cap = sum(avail.get(e.id, {}).values())
        hours = sum(booked.get(e.id, {}).values())
        out[e.id] = round(hours / cap * 100.0, 1) if cap > 0 else 0.0
    return out
