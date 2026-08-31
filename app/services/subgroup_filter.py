"""Фильтр по группам внутри команды — общий для всех витрин.

Второй уровень глобального фильтра приезжает списком идентификаторов групп.
Факт режется по группе задачи, всё «на человека» — по приписке сотрудника,
поэтому здесь два разных выражения, а не одно.

Пустой список означает «команда целиком»: все функции возвращают ``None`` и
вызывающий код оставляет запрос нетронутым. Отсюда и гарантия, что команда без
деления ведёт себя ровно как до правки.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmployeeTeam, Issue, TeamSubgroup


def parse_subgroups_csv(raw: Optional[str]) -> list[str]:
    """Разобрать параметр запроса `subgroups` в список идентификаторов."""
    return [g.strip() for g in (raw.split(",") if raw else []) if g.strip()]


def issue_clause(subgroups: Optional[list[str]]):
    """Условие на задачу: её действующая группа входит в выбранные."""
    if not subgroups:
        return None
    return Issue.effective_subgroup_id.in_(subgroups)


def employee_ids(db: Session, subgroups: Optional[list[str]]) -> Optional[set[str]]:
    """Сотрудники, приписанные к выбранным группам. ``None`` — фильтр не задан."""
    if not subgroups:
        return None
    rows = (
        db.query(EmployeeTeam.employee_id)
        .filter(EmployeeTeam.subgroup_id.in_(subgroups))
        .distinct()
        .all()
    )
    return {emp_id for (emp_id,) in rows}


def names(db: Session, subgroups: Optional[list[str]]) -> dict[str, str]:
    """Подписи групп для заголовков и экспортов."""
    if not subgroups:
        return {}
    rows = (
        db.query(TeamSubgroup.id, TeamSubgroup.name)
        .filter(TeamSubgroup.id.in_(subgroups))
        .all()
    )
    return {gid: name for gid, name in rows}
