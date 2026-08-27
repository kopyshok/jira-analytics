"""Hierarchy rule evaluator.

Decides whether a root-level issue is a "container" (stays as a tree root)
or an operational leaf (collapses into the ``__operations__`` virtual
group). Rule table is evaluated first-match-wins by ``(priority ASC,
created_at ASC)``; if no rule matches, default is ``False``.
"""

from dataclasses import dataclass
from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hierarchy_rule import HierarchyRule


@dataclass(frozen=True)
class EvaluationInput:
    project_key: str
    issue_type: str
    has_parent: bool


def load_rules(db: Session) -> List[HierarchyRule]:
    """Return enabled rules ordered by priority ASC, created_at ASC."""
    stmt = (
        select(HierarchyRule)
        .where(HierarchyRule.is_enabled.is_(True))
        .order_by(HierarchyRule.priority.asc(), HierarchyRule.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())


def classify(rules: List[HierarchyRule], input_: EvaluationInput) -> bool:
    """First-match-wins evaluation. Rules must already be ordered and enabled."""
    for rule in rules:
        if rule.project_key and rule.project_key != input_.project_key:
            continue
        if rule.issue_type and rule.issue_type != input_.issue_type:
            continue
        if rule.require_no_parent and input_.has_parent:
            continue
        return bool(rule.is_container)
    return False


def is_explicit_leaf(rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool) -> bool:
    """True если первое подошедшее правило говорит ``is_container=False``.

    Используется чтобы не пускать leaf-типы (OS/PMD) в backlog/планирование
    даже если они каким-то образом получили категорию initiatives_rfa /
    quarterly_tasks. Порядок тот же first-match-wins по приоритету, что и в
    ``classify`` — иначе широкое правило «проект OS — лист» перебивало бы
    более приоритетное «тип Эпик — контейнер», и OS-Эпики молча выпадали из
    бэклога и сценариев. Если не подошло ни одно правило — False (показываем),
    чтобы новые типы не пропадали.
    """
    inp = EvaluationInput(
        project_key=project_key or "",
        issue_type=issue_type or "",
        has_parent=has_parent,
    )
    for rule in rules:
        if rule.project_key and rule.project_key != inp.project_key:
            continue
        if rule.issue_type and rule.issue_type != inp.issue_type:
            continue
        if rule.require_no_parent and inp.has_parent:
            continue
        return not rule.is_container
    return False
