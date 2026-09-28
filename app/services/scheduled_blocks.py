"""Заблокированные периоды: кого и в какие дни закрывает период.

Период команды X закрывает день человека, если в этот день он состоит в X
(в планах X) или X — его основная команда (в планах любой команды).
Привлечённого в план X (в X не состоит) периоды X не закрывают. Периоды без
команды — для всех.

Приоритет: вся команда < роль < сотрудник. Для человека, команды периода,
месяца и вида работ действуют только периоды самого точного уровня, который
у него есть в этом месяце. Периоды без вида — своя группа. Периоды разных
команд друг друга не перекрывают.

Чистое чтение, без commit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

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
            .where(or_(*conds), ScheduledBlock.start_date <= end, ScheduledBlock.end_date >= start)
            .order_by(ScheduledBlock.start_date, ScheduledBlock.id)
        )
        .scalars()
        .all()
    )
    if not blocks:
        return {}
    role_ids = {r.role_id for b in blocks for r in b.roles}
    code_of = (
        {
            r.id: (r.code or "").lower()
            for r in db.execute(select(Role).where(Role.id.in_(role_ids))).scalars()
        }
        if role_ids
        else {}
    )
    out: Dict[str, Dict[date, BlockHit]] = {}
    for e in emps:
        periods = membership.get(e.id, [])
        role = (e.role or "").lower()
        # (команда периода, год, месяц, вид) → [(уровень, день, период)]
        groups: Dict[tuple, List[tuple]] = defaultdict(list)
        for b in blocks:
            emp_ids = {x.employee_id for x in b.employees}
            b_roles = {code_of.get(x.role_id, "") for x in b.roles}
            if e.id in emp_ids:
                level = EMPLOYEE_LEVEL
            elif role and role in b_roles:
                level = ROLE_LEVEL
            elif not emp_ids and not b.roles:
                level = TEAM_LEVEL
            else:
                continue
            d = max(b.start_date, start)
            last = min(b.end_date, end)
            while d <= last:
                if b.team is None or _active(
                    periods, b.team, d, primary_only=b.team != plan_team
                ):
                    groups[(b.team, d.year, d.month, b.work_type_id)].append((level, d, b))
                d += timedelta(days=1)
        hits: Dict[date, BlockHit] = {}
        for items in groups.values():
            top = max(level for level, _d, _b in items)
            for level, d, b in items:
                if level == top and d not in hits:
                    hits[d] = BlockHit(b.id, b.team, b.work_type_id, b.reason)
        if hits:
            out[e.id] = hits
    return out


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
