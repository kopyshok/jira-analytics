"""Фильтр по группам внутри команды — общий для всех витрин.

Второй уровень глобального фильтра приезжает списком идентификаторов групп.
Факт режется по группе задачи, всё «на человека» — по приписке сотрудника,
поэтому здесь два разных выражения, а не одно.

Отдельное значение ``__none__`` — «Без группы»: задачи и сотрудники, которых
к группе не приписали. Без него сумма по группам не сходилась бы с командой,
а неприписанный человек пропадал бы из витрин.

Пустой список означает «команда целиком»: все функции возвращают ``None`` и
вызывающий код оставляет запрос нетронутым. Отсюда и гарантия, что команда без
деления ведёт себя ровно как до правки.
"""

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import EmployeeTeam, Issue, TeamSubgroup

NO_SUBGROUP_TOKEN = "__none__"


def parse_subgroups_csv(raw: Optional[str]) -> list[str]:
    """Разобрать параметр запроса `subgroups` в список идентификаторов."""
    return [g.strip() for g in (raw.split(",") if raw else []) if g.strip()]


def _split(subgroups: list[str]) -> tuple[list[str], bool]:
    ids = [g for g in subgroups if g != NO_SUBGROUP_TOKEN]
    return ids, NO_SUBGROUP_TOKEN in subgroups


def issue_clause(subgroups: Optional[list[str]]):
    """Условие на задачу: её действующая группа входит в выбранные."""
    if not subgroups:
        return None
    ids, has_none = _split(subgroups)
    clauses = []
    if ids:
        clauses.append(Issue.effective_subgroup_id.in_(ids))
    if has_none:
        clauses.append(Issue.effective_subgroup_id.is_(None))
    if not clauses:
        return None
    return or_(*clauses) if len(clauses) > 1 else clauses[0]


def employee_ids(
    db: Session, subgroups: Optional[list[str]], teams: Optional[list[str]] = None
) -> Optional[set[str]]:
    """Сотрудники, приписанные к выбранным группам. ``None`` — фильтр не задан.

    ``teams`` нужен только для «Без группы»: неприписанного человека ищем
    среди участников выбранных команд, а не по всей базе.
    """
    if not subgroups:
        return None
    ids, has_none = _split(subgroups)

    out: set[str] = set()
    if ids:
        rows = (
            db.query(EmployeeTeam.employee_id)
            .filter(EmployeeTeam.subgroup_id.in_(ids))
            .distinct()
            .all()
        )
        out |= {emp_id for (emp_id,) in rows}
    if has_none:
        q = db.query(EmployeeTeam.employee_id).filter(EmployeeTeam.subgroup_id.is_(None))
        if teams:
            q = q.filter(EmployeeTeam.team.in_(teams))
        out |= {emp_id for (emp_id,) in q.distinct().all()}
    return out


def names(db: Session, subgroups: Optional[list[str]]) -> dict[str, str]:
    """Подписи групп для заголовков и экспортов."""
    if not subgroups:
        return {}
    ids, has_none = _split(subgroups)
    out: dict[str, str] = {}
    if ids:
        rows = (
            db.query(TeamSubgroup.id, TeamSubgroup.name)
            .filter(TeamSubgroup.id.in_(ids))
            .all()
        )
        out.update({gid: name for gid, name in rows})
    if has_none:
        out[NO_SUBGROUP_TOKEN] = "Без группы"
    return out


def roots_matching(
    db: Session, root_ids: list[str], subgroups: Optional[list[str]]
) -> Optional[set[str]]:
    """Инициативы, у которых под ними есть работы выбранных групп.

    Инициативы и эпики заводятся одни на всю команду — своей группы у них
    обычно нет, поэтому решают работы под ними. Инициатива, под которой групп
    вообще не проставили, остаётся видна всем: свежую идею прятать нельзя.

    ``None`` — фильтр не задан.
    """
    if not subgroups or not root_ids:
        return None

    ids, _ = _split(subgroups)

    # Обход вниз по дереву: узел -> его корень-инициатива.
    root_of: dict[str, str] = {rid: rid for rid in root_ids}
    frontier = list(root_ids)
    matched: set[str] = set()
    grouped: set[str] = set()

    while frontier:
        rows = []
        for i in range(0, len(frontier), 400):
            chunk = frontier[i : i + 400]
            rows += (
                db.query(Issue.id, Issue.parent_id, Issue.effective_subgroup_id)
                .filter(Issue.parent_id.in_(chunk))
                .all()
            )
        frontier = []
        for iid, pid, sg in rows:
            if iid in root_of:
                continue
            root = root_of.get(pid)
            if root is None:
                continue
            root_of[iid] = root
            frontier.append(iid)
            if sg:
                grouped.add(root)
                if sg in ids:
                    matched.add(root)

    # Группа у самой инициативы — тоже решение человека, учитываем.
    own = (
        db.query(Issue.id, Issue.effective_subgroup_id)
        .filter(Issue.id.in_(root_ids), Issue.effective_subgroup_id.isnot(None))
        .all()
    )
    for iid, sg in own:
        grouped.add(iid)
        if sg in ids:
            matched.add(iid)

    # Инициатива без единой проставленной группы видна при любом выборе.
    ungrouped = set(root_ids) - grouped
    return matched | ungrouped
