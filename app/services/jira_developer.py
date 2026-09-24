"""«Разработчик» из Jira для инициатив плана.

Поле «Разработчик» (настройка ``jira_developer_field_id``) синк кладёт в
``Issue.developer_account_id``. Для инициативы берётся значение самой задачи,
а если оно пустое или человек не подходит — самый частый «Разработчик» среди
незакрытых задач её поддерева (у RFA разработчики стоят на подзадачах
эпиков; закрытые и отменённые подзадачи не голосуют). Подходит активный
сотрудник с ролью разработчика или без роли, состоявший хоть в какой-то
команде в квартале плана (боты и люди вне команд не подходят). Ничья
решается по учётной записи Jira — ответ не прыгает.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Dict, Iterable

from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.models import BacklogItem, Employee, EmployeeTeam, Issue
from app.services import team_membership as tm
from app.services.backlog_service import CANCEL_STATUSES
from app.services.plan_common import subtree_ids


def jira_developers_for_items(
    db: Session, items: Iterable[BacklogItem], start: date, end: date
) -> Dict[str, str]:
    """{backlog_item_id: employee_id} — только где «Разработчик» нашёлся.

    ``start`` — ``end`` — квартал плана: «Разработчик» должен состоять в
    какой-либо команде хотя бы один его день.
    """
    # Сервис планировщика сам импортирует этот модуль — отсюда только лениво.
    from app.services.resource_planning_service import DEV_ROLES

    roots = {it.id: it.issue_id for it in items if it.issue_id}
    if not roots:
        return {}
    trees = subtree_ids(db, list(roots.values()))
    all_ids = set().union(*trees.values()) if trees else set()
    if not all_ids:
        return {}
    dev_of: Dict[str, str] = {}
    closed: set[str] = set()
    for iid, acc, category, status in (
        db.query(Issue.id, Issue.developer_account_id, Issue.status_category, Issue.status)
        .filter(Issue.id.in_(list(all_ids)), Issue.developer_account_id.isnot(None))
        .all()
    ):
        if not acc:
            continue
        dev_of[iid] = acc
        # Закрыта — как в бэклоге: категория статуса «done» или статус отмены.
        if category == "done" or status in CANCEL_STATUSES:
            closed.add(iid)
    if not dev_of:
        return {}
    emp_by_acc = {
        acc: eid
        for eid, acc, role in db.query(Employee.id, Employee.jira_account_id, Employee.role)
        .filter(
            Employee.jira_account_id.in_(list(set(dev_of.values()))),
            Employee.is_active.is_(True),
            exists().where(
                EmployeeTeam.employee_id == Employee.id,
                *tm.overlaps_clause(start, end),
            ),
        )
        .all()
        if not (role or "").strip() or role.lower() in DEV_ROLES
    }

    out: Dict[str, str] = {}
    for item_id, issue_id in roots.items():
        own = dev_of.get(issue_id)
        if own in emp_by_acc:
            out[item_id] = emp_by_acc[own]
            continue
        counts = Counter(
            dev_of[i]
            for i in trees.get(issue_id, ())
            if i != issue_id and i not in closed and dev_of.get(i) in emp_by_acc
        )
        if counts:
            acc = min(counts, key=lambda a: (-counts[a], a))
            out[item_id] = emp_by_acc[acc]
    return out
