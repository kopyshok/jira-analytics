"""Переток внутри команды — часы, ушедшие из своей группы в соседнюю.

Факт считается по группе задачи, а ёмкость — по группе человека. Разработчик
группы 1, отработавший в направлении группы 2, поэтому виден дважды: его часы
лежат в факте группы 2, а группа 1 обязана видеть, что её ресурс ушёл на
сторону.

Это **не** «помощь извне»: граница «свои — чужие» остаётся на уровне большой
команды, и виджет помощи извне на группы не реагирует.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import EmployeeTeam, Issue, Team, TeamSubgroup, Worklog


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

    emp_group: dict[str, Optional[str]] = {
        emp_id: sg
        for emp_id, sg in db.query(EmployeeTeam.employee_id, EmployeeTeam.subgroup_id)
        .filter(EmployeeTeam.team == team)
        .all()
    }

    rows = (
        db.query(
            Worklog.employee_id,
            Issue.effective_subgroup_id,
            func.sum(Worklog.hours).label("hours"),
        )
        .join(Issue, Issue.id == Worklog.issue_id)
        .filter(
            Issue.team == team,
            Issue.effective_subgroup_id.isnot(None),
            Worklog.started_at >= datetime.combine(from_, datetime.min.time()),
            Worklog.started_at <= datetime.combine(to_, datetime.max.time()),
        )
        .group_by(Worklog.employee_id, Issue.effective_subgroup_id)
        .all()
    )

    acc: dict[str, dict[str, float]] = {
        gid: {"out": 0.0, "in": 0.0} for gid in names
    }
    for employee_id, issue_group, hours in rows:
        own = emp_group.get(employee_id)
        # Человек без приписки и чужак из другой команды перетоком не считаются:
        # у первого нет группы-источника, второй — помощь извне.
        if not own or own == issue_group or own not in acc or issue_group not in acc:
            continue
        acc[own]["out"] += float(hours or 0)
        acc[issue_group]["in"] += float(hours or 0)

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
