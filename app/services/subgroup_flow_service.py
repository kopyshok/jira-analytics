"""Переток внутри команды — часы, ушедшие из своей группы в соседнюю.

Факт считается по группе задачи, а ёмкость — по группе человека. Разработчик
группы 1, отработавший в направлении группы 2, поэтому виден дважды: его часы
лежат в факте группы 2, а группа 1 обязана видеть, что её ресурс ушёл на
сторону.

Группа человека берётся на дату списания: прошлый переток при переводе не
пересчитывается. Работа общего сотрудника в любой из его групп — не переток;
вне их «ушло» делится между его группами по долям, «пришло» — в группу задачи.

Это **не** «помощь извне»: граница «свои — чужие» остаётся на уровне большой
команды, и виджет помощи извне на группы не реагирует. Часы, списанные вне
участия в команде, — помощь извне, в переток они не попадают.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Issue, Team, TeamSubgroup, Worklog
from app.services import subgroup_shares as ss
from app.services import team_membership as tm


@dataclass
class SubgroupFlow:
    """Переток одной группы за период."""

    subgroup_id: str
    subgroup_name: str
    out_hours: float   # часы её людей, отработанные в соседних группах
    in_hours: float    # часы соседей, отработанные в её направлении


def flow_for_team(
    db: Session, team: str, from_: date, to_: date
) -> list[SubgroupFlow]:
    """Переток по каждой группе команды за период.

    Пустой список — у команды выключен признак деления либо перетока не было.
    """
    registry = db.query(Team).filter(Team.name == team).first()
    if registry is None or not registry.has_subgroups:
        return []

    names = {g.id: g.name for g in registry.subgroups}
    if not names:
        return []

    intervals = tm.member_intervals(db, [team], from_, to_)
    if not intervals:
        return []
    records = ss.load_team(db, team, intervals.keys())

    rows = (
        db.query(
            Worklog.employee_id,
            Issue.effective_subgroup_id,
            Worklog.started_at,
            Worklog.hours,
        )
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(
            Issue.team == team,
            Issue.effective_subgroup_id.isnot(None),
            Worklog.employee_id.in_(list(intervals.keys())),
            Worklog.started_at >= datetime.combine(from_, datetime.min.time()),
            Worklog.started_at <= datetime.combine(to_, datetime.max.time()),
        )
        .all()
    )

    acc: dict[str, dict[str, float]] = {
        gid: {"out": 0.0, "in": 0.0} for gid in names
    }
    for employee_id, issue_group, started_at, hours in rows:
        if issue_group not in acc:
            continue
        # Группа человека — на дату списания. Без группы и не участник команды
        # в этот день перетоком не считаются: у первого нет группы-источника,
        # второй — помощь извне. Работа в любой своей группе — не переток.
        day = started_at.date()
        if not tm.day_in_intervals(day, intervals.get(employee_id, [])):
            continue
        shares = ss.shares_on(records.get(employee_id, []), day)
        if not shares or issue_group in shares:
            continue
        h = float(hours or 0)
        for group, part in shares.items():
            if group in acc:
                acc[group]["out"] += h * part
        acc[issue_group]["in"] += h

    return [
        SubgroupFlow(
            subgroup_id=gid,
            subgroup_name=names[gid],
            out_hours=round(v["out"], 2),
            in_hours=round(v["in"], 2),
        )
        for gid, v in acc.items()
        if v["out"] or v["in"]
    ]


def flow_for_teams(
    db: Session, teams: Optional[list[str]], from_: date, to_: date
) -> list[SubgroupFlow]:
    """Переток по нескольким командам сразу — для витрин с общим фильтром."""
    if not teams:
        return []
    out: list[SubgroupFlow] = []
    for team in teams:
        out.extend(flow_for_team(db, team, from_, to_))
    return out
