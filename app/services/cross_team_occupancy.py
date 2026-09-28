"""Занятость сотрудников в планах других команд.

Опорный план команды на квартал — тот, по которому остальные команды видят,
когда её люди заняты: основной (иначе «Готово», иначе самый свежий) план
утверждённого сценария; нет утверждённого — план самого свежего черновика
с признаком «предварительно». Копии-форки не участвуют.

Все функции — чистое чтение, без commit.
"""

from __future__ import annotations

import hashlib
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
from app.services.involvement_default_service import effective_for_phase, teams_defaults
from app.services.plan_common import _plan_sort_key, _quarter_variants, quarter_bounds


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
    # Бронь-привлечение: команда брони человеку не домашняя в квартале её
    # плана (см. `_home_teams`) — не состоял в ней или она не основная.
    # Домашняя команда под такую бронь не подстраивается.
    is_borrowing: bool = False
    # План, для которого собраны брони, уступает человека всем командам: он
    # в команде плана состоит, но она у него не основная.
    yields_here: bool = False
    # Вовлечённость фазы — как её считал планировщик команды брони: своё
    # значение задачи, иначе справочник команды на квартал плана. None — не задана.
    involvement: Optional[float] = None
    # Задача брони: по ней основная команда человека выбирает вид работ.
    backlog_item_id: Optional[str] = None


def _assignment_daily(a: ResourcePlanAssignment) -> Dict[date, float]:
    """Часы фазы по дням: раскладка планировщика, иначе поровну по будням.

    «Поровну» — только для старых строк совсем без раскладки. Пустая
    раскладка — фаза не нашла ни одного свободного дня: часов в днях нет.
    """
    if a.daily_hours_json:
        try:
            raw = json.loads(a.daily_hours_json)
            return {
                date.fromisoformat(k): float(v) for k, v in raw.items() if float(v) > 0
            }
        except (ValueError, TypeError, AttributeError):
            pass
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


def _home_teams(
    periods: Iterable[tuple[str, Optional[date], Optional[date], bool]],
    start: date,
    end: date,
) -> set[str]:
    """Домашние команды сотрудника на отрезке: основная, а без основной — все,
    где он состоял. Домашняя команда не уступает часы человека остальным."""
    active = [
        (t, primary)
        for t, joined, left, primary in periods
        if (joined is None or joined <= end) and (left is None or left > start)
    ]
    return {t for t, primary in active if primary} or {t for t, _ in active}


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
    У каждой брони — ``is_borrowing``: команда брони человеку не домашняя в
    квартале её плана; ``yields_here``: команда ``team`` у него не основная;
    ``involvement`` — вовлечённость фазы.
    Шесть запросов на любой объём: опорные планы двух кварталов, задачи
    планов квартала, назначения, периоды участия их людей и справочник
    вовлечённости их команд.
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
    # Справочник вовлечённости команды брони — на квартал её опорного плана.
    period_of = {
        plan_id: (prev_year, prev_quarter) if plan_id in prev_ids else (year, quarter)
        for plan_id in by_plan
    }
    defaults = teams_defaults(
        db, {(r.team, *period_of[r.plan_id]) for r in by_plan.values()}
    )
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
        periods = membership.get(a.employee_id, ())
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
                is_borrowing=ref.team not in _home_teams(periods, lo, hi),
                yields_here=team is not None
                and _member_of(periods, team, *cur_bounds)
                and team not in _home_teams(periods, *cur_bounds),
                involvement=effective_for_phase(
                    bi, a.phase, defaults[(ref.team, *period_of[a.plan_id])]
                )
                if bi is not None
                else None,
                backlog_item_id=a.backlog_item_id,
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


def other_work_share(
    phases: Iterable[tuple[str, Optional[float], Dict[date, float]]],
) -> Dict[str, Dict[date, float]]:
    """{сотрудник: {день: доля дня на прочие работы}} по фазам дня.

    ``phases`` — фазы как (сотрудник, вовлечённость, часы по дням).
    Вовлечённость 90% — это 10% дня на прочие (нормированные) работы. Несколько
    фаз в день — берётся наименьшая вовлечённость. Фаза без вовлечённости
    доли не задаёт: такой день берёт долю человека (см. `base_other_share`).
    """
    acc: Dict[str, Dict[date, float]] = defaultdict(dict)
    for employee_id, involvement, daily in phases:
        if involvement is None:
            continue
        share = 1.0 - max(0.0, min(1.0, involvement))
        for d, h in daily.items():
            if h > 0 and share > acc[employee_id].get(d, -1.0):
                acc[employee_id][d] = share
    return {eid: days for eid, days in acc.items() if days}


def base_other_share(
    db: Session,
    employees: Iterable[Employee],
    year: Optional[int],
    quarter: Optional[int],
) -> Dict[str, float]:
    """{сотрудник: доля дня на прочие работы в день без задач}.

    Прочие нормированные работы у человека каждый рабочий день. Их доля —
    по справочнику вовлечённости его домашней команды (основной, а без неё —
    всех его команд; берётся наименьшая вовлечённость) для его роли:
    разработчик — «Разработка», аналитик, РП и консультант — «Анализ».
    Нет значения — доли нет. Три запроса на любой объём.
    """
    # Сервис планировщика сам импортирует этот модуль — отсюда только лениво.
    from app.services.resource_planning_service import ANALYST_ROLES, DEV_ROLES

    if not year or not quarter:
        return {}
    phase_of = {}
    for e in employees:
        role = (e.role or "").lower()
        phase = "dev" if role in DEV_ROLES else "analyst" if role in ANALYST_ROLES else None
        if phase:
            phase_of[e.id] = phase
    if not phase_of:
        return {}
    lo, hi = quarter_bounds(year, quarter)
    membership = tm.membership_rows(db, list(phase_of))
    homes = {eid: _home_teams(membership.get(eid, ()), lo, hi) for eid in phase_of}
    defaults = teams_defaults(
        db, {(t, year, quarter) for teams in homes.values() for t in teams}
    )
    out: Dict[str, float] = {}
    for eid, phase in phase_of.items():
        invs = [
            defaults[(t, year, quarter)][phase]
            for t in homes[eid]
            if phase in defaults[(t, year, quarter)]
        ]
        if invs:
            out[eid] = 1.0 - max(0.0, min(1.0, min(invs)))
    return out


def occupied_hours(
    bookings: Iterable[ExternalBooking],
    capacity: Dict[str, Dict[date, float]],
    base_share: Optional[Dict[str, float]] = None,
) -> Dict[str, Dict[date, float]]:
    """{сотрудник: {день брони: часы броней вместе с прочими работами}}.

    В день брони человек занят не только её часами, но и долей прочих работ
    от ёмкости дня (``capacity``, см. `other_work_share`; у броней без
    вовлечённости — доля человека ``base_share``): другой команде свободен
    только остаток. Так же следующая фаза своего плана видит остаток дня за
    вычетом потолка вовлечённости предыдущей.
    """
    bookings = list(bookings)
    base = base_share or {}
    share = other_work_share((b.employee_id, b.involvement, b.daily_hours) for b in bookings)
    return {
        eid: {
            d: h
            + capacity.get(eid, {}).get(d, 0.0)
            * share.get(eid, {}).get(d, base.get(eid, 0.0))
            for d, h in days.items()
        }
        for eid, days in daily_totals(bookings).items()
    }


def busy_hours(
    bookings: Iterable[ExternalBooking],
    capacity: Dict[str, Dict[date, float]],
    base_share: Dict[str, float],
) -> Dict[str, Dict[date, float]]:
    """{сотрудник: {день: занято бронями и прочими работами}} на все дни ``capacity``.

    В дни броней — `occupied_hours`, в остальные — прочие работы по доле
    человека ``base_share``: они есть каждый рабочий день.
    """
    occupied = occupied_hours(bookings, capacity, base_share)
    return {
        eid: {
            d: occupied.get(eid, {}).get(d, h * base_share.get(eid, 0.0))
            for d, h in days.items()
        }
        for eid, days in capacity.items()
    }


def subtractable(
    bookings: Iterable[ExternalBooking], borrowed: set
) -> List[ExternalBooking]:
    """Брони, которые вычитаются из доступности плана: сначала домашняя команда.

    Привлечённому в план (``borrowed``) и тому, у кого команда плана не
    основная (``yields_here``), — все брони других команд. Своему сотруднику
    в домашней команде — только брони других его домашних команд (нет
    основной — все его команды равны). Бронь-привлечение доступность не
    уменьшает — подстраивается привлекающая команда.
    """
    return [
        b
        for b in bookings
        if b.employee_id in borrowed or b.yields_here or not b.is_borrowing
    ]


def _team_hashes(
    bookings: Iterable[ExternalBooking],
    blocked_cells: Optional[Dict[str, List[tuple]]] = None,
) -> Dict[str, str]:
    """{команда: sha256 её броней и заблокированных дней её периодов}.

    Брони — по часам человека в день. Строки брони (их id, фазы, дробление
    на части) в отпечаток не входят: пересчёт чужого плана пересоздаёт
    строки, и если часы людей по дням те же, отпечаток не меняется.
    ``blocked_cells`` — {команда: [(сотрудник, день ISO)]}, заблокированные
    дни периодов основных команд людей плана (`scheduled_blocks.cells_by_team`).
    Команда без заблокированных дней хэшируется как раньше — старые
    отпечатки планов без периодов чужих команд не устаревают.
    """
    hours: Dict[str, Dict[tuple, float]] = defaultdict(lambda: defaultdict(float))
    for b in bookings:
        for d, h in b.daily_hours.items():
            hours[b.team][(b.employee_id, d.isoformat())] += h
    cells_of = blocked_cells or {}
    out: Dict[str, str] = {}
    for team in set(hours) | set(cells_of):
        rows = sorted(
            (eid, day, round(h, 2))
            for (eid, day), h in hours.get(team, {}).items()
            if round(h, 2) > 0
        )
        cells = sorted(list(c) for c in cells_of.get(team, ()))
        if not rows and not cells:
            continue
        payload = rows if not cells else {"blocked": cells, "hours": rows}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        out[team] = hashlib.sha256(raw).hexdigest()
    return out


def fingerprint(
    bookings: Iterable[ExternalBooking],
    blocked_cells: Optional[Dict[str, List[tuple]]] = None,
) -> str:
    """Отпечаток броней по командам — JSON {команда: sha256}.

    План запоминает его при расчёте по вычтенным из своей доступности
    броням (``ResourcePlan.external_fingerprint``), диаграмма сверяет с ним
    текущие — см. `stale_teams`. ``blocked_cells`` — заблокированные дни
    периодов основных команд людей плана (см. `_team_hashes`).
    """
    return json.dumps(_team_hashes(bookings, blocked_cells), sort_keys=True)


def stale_teams(
    stored: Optional[str],
    bookings: Iterable[ExternalBooking],
    computed_at: Optional[datetime],
    blocked_cells: Optional[Dict[str, List[tuple]]] = None,
) -> List[str]:
    """Команды, чьи вычитаемые брони разошлись с учтёнными при расчёте, по алфавиту.

    ``stored`` — отпечаток, запомненный планом при расчёте (`fingerprint`),
    ``bookings`` — брони, вычитаемые из доступности плана сейчас. Команда
    попадает в список, если её брони появились, пропали или сдвинулись.
    Пересчёт чужого плана с той же раскладкой план не старит — поэтому два
    плана с общим сотрудником не помечают друг друга без конца.
    План ни разу не считался — сравнивать не с чем, список пуст. Посчитан,
    пока планы не запоминали отпечаток (``stored`` пуст), — какие брони он
    учёл, неизвестно: устарел, если вычитаемые брони вообще есть.
    ``blocked_cells`` — заблокированные дни периодов основных команд людей
    плана сейчас: изменился период основной команды — она тоже в списке.
    """
    if computed_at is None:
        return []
    now = _team_hashes(bookings, blocked_cells)
    if stored is None:
        return sorted(now)
    was = json.loads(stored)
    return sorted(t for t in set(was) | set(now) if was.get(t) != now.get(t))


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


def guest_ids(
    db: Session,
    team: Optional[str],
    start: date,
    end: date,
    employee_ids: Iterable[Optional[str]],
) -> set[str]:
    """Кто из перечисленных состоит в ``team`` в периоде, но она у него не
    основная: план ``team`` уступает его другим командам, как привлечённого."""
    if not team:
        return set()
    ids = [e for e in dict.fromkeys(employee_ids) if e]
    membership = tm.membership_rows(db, ids)
    return {
        e
        for e in ids
        if _member_of(membership.get(e, ()), team, start, end)
        and team not in _home_teams(membership.get(e, ()), start, end)
    }


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
    avail = ResourcePlanningService(db).build_availability(employees, start, end)
    out: Dict[str, float] = {}
    for e in employees:
        cap = sum(avail.get(e.id, {}).values())
        hours = sum(booked.get(e.id, {}).values())
        out[e.id] = round(hours / cap * 100.0, 1) if cap > 0 else 0.0
    return out
