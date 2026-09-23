"""«Разработчик» из Jira для инициатив плана.

Поле «Разработчик» (настройка ``jira_developer_field_id``) синк кладёт в
``Issue.developer_account_id``. Для инициативы берётся значение самой задачи,
а если оно пустое или человек не найден среди активных — самый частый
«Разработчик» во всём её поддереве (у RFA разработчики стоят на подзадачах
эпиков). Ничья решается по учётной записи Jira — ответ не прыгает.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable

from sqlalchemy.orm import Session

from app.models import BacklogItem, Employee, Issue
from app.services.plan_common import subtree_ids


def jira_developers_for_items(
    db: Session, items: Iterable[BacklogItem]
) -> Dict[str, str]:
    """{backlog_item_id: employee_id} — только где «Разработчик» нашёлся."""
    roots = {it.id: it.issue_id for it in items if it.issue_id}
    if not roots:
        return {}
    trees = subtree_ids(db, list(roots.values()))
    all_ids = set().union(*trees.values()) if trees else set()
    if not all_ids:
        return {}
    dev_of = {
        iid: acc
        for iid, acc in db.query(Issue.id, Issue.developer_account_id)
        .filter(Issue.id.in_(list(all_ids)), Issue.developer_account_id.isnot(None))
        .all()
        if acc
    }
    if not dev_of:
        return {}
    emp_by_acc = {
        acc: eid
        for eid, acc in db.query(Employee.id, Employee.jira_account_id)
        .filter(
            Employee.jira_account_id.in_(list(set(dev_of.values()))),
            Employee.is_active.is_(True),
        )
        .all()
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
            if i != issue_id and dev_of.get(i) in emp_by_acc
        )
        if counts:
            acc = min(counts, key=lambda a: (-counts[a], a))
            out[item_id] = emp_by_acc[acc]
    return out
