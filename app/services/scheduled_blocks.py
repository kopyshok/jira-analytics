"""Заблокированные периоды: кого и в какие дни закрывает период.

Период команды X закрывает день человека, если в этот день он состоит в X
(в планах X) или X — его основная команда (в планах любой команды).
Привлечённого в план X (в X не состоит) периоды X не закрывают. Периоды без
команды — для всех.

Приоритет: вся команда < роль < сотрудник. Для человека, команды периода,
месяца и вида работ действуют только периоды самого точного уровня, который
у него есть в этом месяце. Периоды без вида — своя группа. Периоды разных
команд друг друга не перекрывают. В один день — один период: период команды
раньше периода без команды.

Чистое чтение, без commit.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import Employee, Role, ScheduledBlock
from app.services import team_membership as tm

TEAM_LEVEL, ROLE_LEVEL, EMPLOYEE_LEVEL = 0, 1, 2


@dataclass(frozen=True)
class BlockHit:
    """Заблокированный день человека: какой период его закрывает."""

    block_id: str
    team: Optional[str]
    work_type_id: Optional[str]
    reason: str


@dataclass(frozen=True)
class NotApplied:
    """Кого период не закрывает в месяце: там у человека период того же вида
    точнее уровнем (по роли или лично)."""

    employee_id: str
    month: date  # первое число месяца
    by_level: int


def _level(b: ScheduledBlock, emp_id: str, role: str, code_of: Dict[str, str]) -> Optional[int]:
    """Уровень периода для человека: лично, по роли, вся команда; None — не его."""
    emp_ids = {x.employee_id for x in b.employees}
    if emp_id in emp_ids:
        return EMPLOYEE_LEVEL
    if role and role in {code_of.get(x.role_id, "") for x in b.roles}:
        return ROLE_LEVEL
    if not emp_ids and not b.roles:
        return TEAM_LEVEL
    return None


def _role_codes(db: Session, blocks: Sequence[ScheduledBlock]) -> Dict[str, str]:
    role_ids = {r.role_id for b in blocks for r in b.roles}
    if not role_ids:
        return {}
    return {
        r.id: (r.code or "").lower()
        for r in db.execute(select(Role).where(Role.id.in_(role_ids))).scalars()
    }


def _active(periods, team: str, day: date, primary_only: bool) -> bool:
    """Состоит ли человек в ``team`` в этот день (``primary_only`` — и она основная)."""
    return any(
        t == team
        and (is_primary or not primary_only)
        and (joined is None or joined <= day)
        and (left is None or left > day)
        for t, joined, left, is_primary in periods
    )


def resolve_blocked_days(
    db: Session,
    employees: Iterable[Employee],
    start: date,
    end: date,
    plan_team: Optional[str],
) -> Dict[str, Dict[date, BlockHit]]:
    """{сотрудник: {день: период}} — заблокированные дни людей в плане ``plan_team``.

    ``plan_team=None`` — вне плана: только периоды основных команд и общие.
    Пять запросов на любой объём: периоды участия, периоды, их роли и
    сотрудники (selectinload), коды ролей.
    """
    emps = [e for e in employees if e is not None]
    if not emps or start > end:
        return {}
    # Приоритет решается в пределах месяца: окно расширяем до целых месяцев,
    # иначе окно в день видит не те периоды, что квартал. Итог — по [start, end].
    m_start = start.replace(day=1)
    m_end = date(end.year, end.month, calendar.monthrange(end.year, end.month)[1])
    membership = tm.membership_rows(db, [e.id for e in emps])
    teams = {t for rows in membership.values() for t, _j, _l, primary in rows if primary}
    if plan_team:
        teams.add(plan_team)
    conds = [ScheduledBlock.team.is_(None)]
    if teams:
        conds.append(ScheduledBlock.team.in_(sorted(teams)))
    blocks = (
        db.execute(
            select(ScheduledBlock)
            .options(selectinload(ScheduledBlock.roles), selectinload(ScheduledBlock.employees))
            .where(or_(*conds), ScheduledBlock.start_date <= m_end, ScheduledBlock.end_date >= m_start)
            .order_by(ScheduledBlock.start_date, ScheduledBlock.id)
        )
        .scalars()
        .all()
    )
    if not blocks:
        return {}
    code_of = _role_codes(db, blocks)
    out: Dict[str, Dict[date, BlockHit]] = {}
    for e in emps:
        periods = membership.get(e.id, [])
        role = (e.role or "").lower()
        # (команда периода, год, месяц, вид) → [(уровень, день, период)]
        groups: Dict[tuple, List[tuple]] = defaultdict(list)
        for b in blocks:
            level = _level(b, e.id, role, code_of)
            if level is None:
                continue
            d = max(b.start_date, m_start)
            last = min(b.end_date, m_end)
            while d <= last:
                if b.team is None or _active(
                    periods, b.team, d, primary_only=b.team != plan_team
                ):
                    groups[(b.team, d.year, d.month, b.work_type_id)].append((level, d, b))
                d += timedelta(days=1)
        hits: Dict[date, BlockHit] = {}
        # Один период на день: период команды раньше периода без команды —
        # иначе свой период команды прячется и его расход запаса теряется.
        for key in sorted(groups, key=lambda k: k[0] is None):
            items = groups[key]
            top = max(level for level, _d, _b in items)
            for level, d, b in items:
                if level == top and start <= d <= end and d not in hits:
                    hits[d] = BlockHit(b.id, b.team, b.work_type_id, b.reason)
        if hits:
            out[e.id] = hits
    return out


def _month_bounds(d: date) -> tuple[date, date]:
    return d.replace(day=1), date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def not_applied(db: Session, blocks: Sequence[ScheduledBlock]) -> Dict[str, List[NotApplied]]:
    """{период: [кого он не закрывает и в каком месяце]} — для списка периодов.

    Правило то же, что в ``resolve_blocked_days``: в месяце и виде работ у
    человека действуют только периоды самого точного уровня. Период команды
    не закрывает тех, у кого в этом месяце есть период того же вида по роли
    или лично, — даже если даты не совпадают. Учитываются участники команды
    периода в его дни; периоды без команды не проверяются.
    """
    own = [b for b in blocks if b.team]
    if not own:
        return {}
    teams = sorted({b.team for b in own if b.team})
    lo = _month_bounds(min(b.start_date for b in own))[0]
    hi = _month_bounds(max(b.end_date for b in own))[1]
    rivals = (
        db.execute(
            select(ScheduledBlock)
            .options(selectinload(ScheduledBlock.roles), selectinload(ScheduledBlock.employees))
            .where(ScheduledBlock.team.in_(teams), ScheduledBlock.start_date <= hi,
                   ScheduledBlock.end_date >= lo)
        )
        .scalars()
        .all()
    )
    code_of = _role_codes(db, list(rivals) + own)
    out: Dict[str, List[NotApplied]] = defaultdict(list)
    for team in teams:
        intervals = tm.member_intervals(db, [team], lo, hi)
        if not intervals:
            continue
        people = db.query(Employee).filter(Employee.id.in_(list(intervals))).all()

        def active(emp_id: str, a: date, b: date) -> bool:
            return any(s <= b and e >= a for s, e in intervals[emp_id])

        for blk in (x for x in own if x.team == team):
            month = blk.start_date.replace(day=1)
            while month <= blk.end_date:
                m_lo, m_hi = _month_bounds(month)
                days = (max(blk.start_date, m_lo), min(blk.end_date, m_hi))
                same = [
                    r for r in rivals
                    if r.team == team and r.work_type_id == blk.work_type_id
                    and r.start_date <= m_hi and r.end_date >= m_lo
                ]
                for e in people:
                    role = (e.role or "").lower()
                    level = _level(blk, e.id, role, code_of)
                    if level is None or not active(e.id, *days):
                        continue
                    top = max(
                        (lv for r in same
                         if (lv := _level(r, e.id, role, code_of)) is not None
                         and active(e.id, max(r.start_date, m_lo), min(r.end_date, m_hi))),
                        default=level,
                    )
                    if top > level:
                        out[blk.id].append(NotApplied(e.id, m_lo, top))
                month = m_hi + timedelta(days=1)
    return dict(out)


def cells_by_team(
    hits: Dict[str, Dict[date, BlockHit]], exclude_team: Optional[str]
) -> Dict[str, List[tuple[str, str]]]:
    """{команда: [(сотрудник, день ISO)]} — заблокированные дни чужих основных
    команд людей плана, для отпечатка плана (`cross_team_occupancy.fingerprint`).
    Периоды самой команды плана и общие периоды не входят."""
    out: Dict[str, List[tuple[str, str]]] = defaultdict(list)
    for eid, by_day in hits.items():
        for d, hit in by_day.items():
            if hit.team is not None and hit.team != exclude_team:
                out[hit.team].append((eid, d.isoformat()))
    return {t: sorted(cells) for t, cells in out.items()}
