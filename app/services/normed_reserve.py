"""Запас нормированных работ команды на квартал и его раскладка по дням.

Нормированные работы — запас времени на квартал по видам работ: процент нормы
по ролям из опорного сценария команды (утверждённый, иначе свежий черновик;
правила роли заменяют правила «для всех ролей»; только виды, которые
уменьшают запас на проекты). Люди запаса — те, у кого команда основная, и
только в эти дни. Норма дня — производственный календарь минус отсутствия;
заблокированные периоды норму не уменьшают: они сами нормированная работа.

Расход с датой: заблокированный период команды с видом работ (весь день) и
работа в опорных планах других команд (вид — выбранный командой для задачи,
иначе «Технические задачи»). Остаток вида делится между людьми роли
пропорционально их норме.

Чистое чтение, без commit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    Employee,
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ScenarioRule,
    TeamWorkTypeOverride,
)
from app.services import cross_team_occupancy as cto
from app.services import scheduled_blocks as sb
from app.services import team_membership as tm
from app.services.plan_common import _quarter_variants, quarter_bounds

DEFAULT_HOURS_PER_DAY = 8.0
# Вид, которым основная команда по умолчанию считает работу своих людей в
# планах других команд.
CROSS_TEAM_WORK_TYPE_CODE = "technical_tasks"
BLOCK_WITHOUT_TYPE = "Заблокировано (вид не указан)"


def reference_scenario(
    db: Session, team: str, year: int, quarter: int
) -> Optional[PlanningScenario]:
    """Опорный сценарий команды на квартал: утверждённый, иначе свежий черновик."""
    rows = (
        db.execute(
            select(PlanningScenario).where(
                PlanningScenario.team == team,
                PlanningScenario.year == year,
                PlanningScenario.quarter.in_(_quarter_variants(quarter)),
                PlanningScenario.status.in_(("approved", "draft")),
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return None
    return max(
        rows,
        key=lambda s: (s.status == "approved", s.updated_at or s.created_at or datetime.min, s.id),
    )


def calendar_hours(db: Session, start: date, end: date) -> Dict[date, float]:
    """{рабочий день: часы}: производственный календарь, иначе 8 ч в будни."""
    anomalies = {
        r.date: float(r.hours)
        for r in db.execute(
            select(ProductionCalendarDay).where(
                ProductionCalendarDay.date >= start, ProductionCalendarDay.date <= end
            )
        ).scalars()
    }
    out: Dict[date, float] = {}
    d = start
    while d <= end:
        h = anomalies.get(d, DEFAULT_HOURS_PER_DAY if d.weekday() < 5 else 0.0)
        if h > 0:
            out[d] = h
        d += timedelta(days=1)
    return out


def absent_days(
    db: Session, employee_ids: Iterable[str], start: date, end: date
) -> Dict[str, set]:
    """{сотрудник: дни отсутствий} внутри окна (конец отсутствия включительно)."""
    ids = list(employee_ids)
    out: Dict[str, set] = defaultdict(set)
    if not ids:
        return out
    for a in db.execute(
        select(Absence).where(
            Absence.employee_id.in_(ids), Absence.start_date <= end, Absence.end_date >= start
        )
    ).scalars():
        d = max(a.start_date, start)
        while d <= min(a.end_date, end):
            out[a.employee_id].add(d)
            d += timedelta(days=1)
    return out


def primary_on(periods, team: Optional[str], day: date) -> bool:
    """Основная ли ``team`` у человека в этот день (``periods`` — из membership_rows)."""
    return any(
        t == team and is_primary and (j is None or j <= day) and (lv is None or lv > day)
        for t, j, lv, is_primary in periods
    )


@dataclass
class WorkTypeReserve:
    """Запас вида работ роли и его расход с датой, часы."""

    work_type_id: str
    label: str
    planned: float = 0.0
    blocked: float = 0.0
    other_teams: float = 0.0

    @property
    def used(self) -> float:
        return self.blocked + self.other_teams

    @property
    def remaining(self) -> float:
        return max(0.0, self.planned - self.used)

    @property
    def overuse(self) -> float:
        return max(0.0, self.used - self.planned)


@dataclass
class PersonReserve:
    """Нормированные работы человека в запасе своей основной команды, часы."""

    employee_id: str
    role: Optional[str]
    norm: float
    blocked: Dict[str, float] = field(default_factory=dict)
    share: Dict[str, float] = field(default_factory=dict)

    @property
    def undated(self) -> float:
        """Доля остатков — нормированные работы без даты."""
        return sum(self.share.values())


@dataclass
class OtherTeamWork:
    """Работа людей одной роли команды над задачей другой команды за квартал.

    ``role`` — код роли, как ключ в ``TeamReserve.roles`` (без роли — «»).
    Вид работ — выбор команды для задачи, общий для всех ролей.
    """

    backlog_item_id: str
    issue_key: Optional[str]
    title: str
    team: str
    role: str
    hours: float
    work_type_id: str
    is_manual: bool


@dataclass
class TeamReserve:
    team: str
    scenario_id: str
    scenario_name: str
    roles: Dict[str, List[WorkTypeReserve]]
    people: Dict[str, PersonReserve]
    other_team_work: List[OtherTeamWork]
    # Все виды, уменьшающие запас на проекты: {id: подпись} — для выбора.
    labels: Dict[str, str]


def team_reserve(
    db: Session, team: str, year: int, quarter: int | str
) -> Optional[TeamReserve]:
    """Запас нормированных работ команды на квартал; None — у команды нет правил.

    Квартал — число или текст («Q4», «4»), как в планах и сценариях.
    Запросов — константа на команду: сценарий, виды, правила, календарь,
    состав, периоды участия, отсутствия, сотрудники, периоды (резолвер),
    выбор видов, брони других команд.
    """
    q = cto.quarter_num(quarter)
    if q is None:
        return None
    scenario = reference_scenario(db, team, year, q)
    if scenario is None:
        return None
    types = {
        w.id: w
        for w in db.execute(
            select(MandatoryWorkType).where(MandatoryWorkType.subtracts_from_pool == True)  # noqa: E712
        ).scalars()
    }
    # Роль заводится любым своим правилом, даже 0%: её правила заменяют
    # правила «для всех ролей» (как в `ResourceBaseService._pool_share`).
    percents: Dict[Optional[str], Dict[str, float]] = defaultdict(dict)
    for rule in db.execute(select(ScenarioRule).where(ScenarioRule.scenario_id == scenario.id)).scalars():
        if rule.work_type_id not in types:
            continue
        by_type = percents[rule.role]
        if rule.percent_of_norm:
            by_type[rule.work_type_id] = (
                by_type.get(rule.work_type_id, 0.0) + float(rule.percent_of_norm)
            )
    if not any(percents.values()):
        return None

    def pct_of(role: Optional[str]) -> Dict[str, float]:
        return percents[role] if role and role in percents else percents.get(None, {})

    q_start, q_end = quarter_bounds(year, q)
    cal = calendar_hours(db, q_start, q_end)
    ids = sorted(tm.members_overlapping(db, [team], q_start, q_end))
    membership = tm.membership_rows(db, ids)
    absent = absent_days(db, ids, q_start, q_end)
    norm_day: Dict[str, Dict[date, float]] = {}
    for eid in ids:
        days = {
            d: h
            for d, h in cal.items()
            if d not in absent.get(eid, ()) and primary_on(membership.get(eid, ()), team, d)
        }
        if days:
            norm_day[eid] = days
    employees = (
        {e.id: e for e in db.execute(select(Employee).where(Employee.id.in_(list(norm_day)))).scalars()}
        if norm_day
        else {}
    )

    # Все виды строк — из ``types``: правила, периоды и выбор видов
    # отфильтрованы по ним ниже.
    rows: Dict[tuple, WorkTypeReserve] = {}

    def row(role: str, wt: str) -> WorkTypeReserve:
        if (role, wt) not in rows:
            rows[(role, wt)] = WorkTypeReserve(wt, types[wt].label)
        return rows[(role, wt)]

    people: Dict[str, PersonReserve] = {}
    for eid, days in norm_day.items():
        e = employees.get(eid)
        if e is None:
            continue
        norm = sum(days.values())
        people[eid] = PersonReserve(eid, e.role, norm)
        for wt, pct in pct_of(e.role).items():
            row(e.role or "", wt).planned += norm * pct / 100.0

    # Заблокированные периоды команды — весь день, в дни, когда она основная.
    # Период вида, который не уменьшает запас на проекты, запас не тратит.
    hits = sb.resolve_blocked_days(db, [employees[i] for i in people], q_start, q_end, team)
    for eid, by_day in hits.items():
        p = people[eid]
        for d, hit in by_day.items():
            if hit.team != team or hit.work_type_id not in types or d not in norm_day[eid]:
                continue
            h = norm_day[eid][d]
            p.blocked[hit.work_type_id] = p.blocked.get(hit.work_type_id, 0.0) + h
            row(p.role or "", hit.work_type_id).blocked += h

    # Работа в опорных планах других команд.
    default_wt = next((w.id for w in types.values() if w.code == CROSS_TEAM_WORK_TYPE_CODE), None)
    overrides = {
        o.backlog_item_id: o.work_type_id
        for o in db.execute(
            select(TeamWorkTypeOverride).where(TeamWorkTypeOverride.team == team)
        ).scalars()
        if o.work_type_id in types
    }
    work: Dict[tuple, OtherTeamWork] = {}
    for b in cto.external_bookings(
        db, team=team, year=year, quarter=q,
        employee_ids=list(people), start=q_start, end=q_end,
    ):
        days = norm_day.get(b.employee_id, {})
        hours = sum(h for d, h in b.daily_hours.items() if d in days)
        manual = b.backlog_item_id in overrides
        b_wt = overrides.get(b.backlog_item_id or "") or default_wt
        if hours <= 0 or b_wt is None:
            continue
        role = people[b.employee_id].role or ""
        row(role, b_wt).other_teams += hours
        key = (b.backlog_item_id, b.team, role)
        if key not in work:
            work[key] = OtherTeamWork(
                b.backlog_item_id or "", b.issue_key, b.title, b.team, role, 0.0, b_wt, manual
            )
        work[key].hours += hours

    # Остаток вида — людям роли пропорционально норме.
    norm_by_role: Dict[str, float] = defaultdict(float)
    for p in people.values():
        norm_by_role[p.role or ""] += p.norm
    for (role, wt), r in rows.items():
        if r.remaining <= 0 or norm_by_role[role] <= 0:
            continue
        for p in people.values():
            if (p.role or "") == role:
                p.share[wt] = r.remaining * p.norm / norm_by_role[role]

    def order(r: WorkTypeReserve) -> tuple:
        w = types.get(r.work_type_id)
        return (w.sort_order if w else 999, r.label)

    roles_out: Dict[str, List[WorkTypeReserve]] = defaultdict(list)
    for (role, _wt), r in rows.items():
        roles_out[role].append(r)
    return TeamReserve(
        team=team,
        scenario_id=scenario.id,
        scenario_name=scenario.name,
        roles={role: sorted(rs, key=order) for role, rs in roles_out.items()},
        people=people,
        other_team_work=sorted(work.values(), key=lambda w: (-w.hours, w.issue_key or "")),
        labels={
            wt: w.label
            for wt, w in sorted(types.items(), key=lambda kv: (kv[1].sort_order, kv[1].label))
        },
    )


def merge_person(
    reserves: Iterable[Optional[TeamReserve]], employee_id: str
) -> Optional[PersonReserve]:
    """Нормированные работы человека по всем его основным командам квартала
    (основная менялась внутри квартала — доли складываются)."""
    parts = [r.people[employee_id] for r in reserves if r is not None and employee_id in r.people]
    if not parts:
        return None
    out = PersonReserve(employee_id, parts[0].role, sum(p.norm for p in parts))
    for p in parts:
        for wt, h in p.blocked.items():
            out.blocked[wt] = out.blocked.get(wt, 0.0) + h
        for wt, h in p.share.items():
            out.share[wt] = out.share.get(wt, 0.0) + h
    return out


@dataclass
class PersonLoad:
    """Загрузка человека за квартал с нормированными работами, часы."""

    normed_by_day: Dict[date, float]
    blocked: Dict[date, sb.BlockHit]
    capacity: float
    own: float
    other_teams: float
    normed: float
    unplaced: float
    normed_by_type: Dict[str, float]

    @property
    def pct(self) -> float:
        total = self.own + self.other_teams + self.normed
        return total / self.capacity * 100.0 if self.capacity > 0 else 0.0


def place_person(
    capacity: Dict[date, float],
    own: Dict[date, float],
    other_teams: Dict[date, float],
    residue_share: Dict[date, float],
    blocked: Dict[date, sb.BlockHit],
    reserve: Optional[PersonReserve],
    labels: Dict[str, str],
) -> PersonLoad:
    """Раскладка нормированных работ человека по дням (для показа).

    ``capacity`` — норма рабочих дней квартала (календарь минус отсутствия),
    ``own``/``other_teams`` — часы задач плана и броней других команд,
    ``residue_share`` — доля дня вне задачи по вовлечённости (см.
    `cross_team_occupancy.other_work_share`), ``blocked`` — заблокированные
    дни. Заблокированный день — вся норма дня. В день с задачей — остаток
    дня после вовлечённости, пока хватает доли человека. Остаток доли —
    сначала на дни без задач (ни своих, ни других команд) пропорционально их
    свободным часам, то есть поровну по дню, а сокращённому дню меньше; не
    хватило — на свободное время дней с задачами, тоже пропорционально. Не
    поместилось — ``unplaced``.
    """
    normed = {d: 0.0 for d in capacity}
    by_type: Dict[str, float] = defaultdict(float)
    for d, hit in blocked.items():
        if d in capacity:
            normed[d] = capacity[d]
            by_type[labels.get(hit.work_type_id or "", BLOCK_WITHOUT_TYPE)] += capacity[d]
    undated = reserve.undated if reserve else 0.0
    if reserve:
        for wt, h in reserve.share.items():
            by_type[labels.get(wt, wt)] += h
    remaining = undated
    busy = {d: own.get(d, 0.0) + other_teams.get(d, 0.0) for d in capacity}
    for d in sorted(capacity):
        if remaining <= 0:
            break
        if d in blocked or busy[d] <= 0:
            continue
        r = min(max(0.0, capacity[d] - busy[d]), capacity[d] * residue_share.get(d, 0.0), remaining)
        normed[d] += r
        remaining -= r

    def spread(free: Dict[date, float], rest: float) -> float:
        """Разложить ``rest`` по свободным часам ``free`` пропорционально; вернуть,
        что не поместилось."""
        total = sum(free.values())
        if rest <= 0 or total <= 0:
            return rest
        k = min(1.0, rest / total)
        for d, f in free.items():
            normed[d] += f * k
        return max(0.0, rest - total)

    free = {
        d: max(0.0, capacity[d] - busy[d] - normed[d]) for d in capacity if d not in blocked
    }
    remaining = spread({d: f for d, f in free.items() if busy[d] <= 0}, remaining)
    remaining = spread({d: f for d, f in free.items() if busy[d] > 0}, remaining)
    return PersonLoad(
        normed_by_day=normed,
        blocked={d: h for d, h in blocked.items() if d in capacity},
        capacity=sum(capacity.values()),
        own=sum(own.get(d, 0.0) for d in capacity),
        other_teams=sum(other_teams.get(d, 0.0) for d in capacity),
        normed=sum(capacity[d] for d in blocked if d in capacity) + undated,
        unplaced=remaining,
        normed_by_type=dict(by_type),
    )
