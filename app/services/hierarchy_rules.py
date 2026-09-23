"""Hierarchy rule evaluator.

Decides whether a root-level issue is a "container" (stays as a tree root)
or an operational leaf (collapses into the ``__operations__`` virtual
group). Rule table is evaluated first-match-wins by ``(priority ASC,
created_at ASC)``; if no rule matches, default is ``False``.
"""

from dataclasses import dataclass
from typing import List, Optional

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


def matches(rule: HierarchyRule, input_: EvaluationInput) -> bool:
    """Все предикаты правила проходят на задаче."""
    if rule.project_key and rule.project_key != input_.project_key:
        return False
    if rule.issue_type and rule.issue_type != input_.issue_type:
        return False
    if rule.require_no_parent and input_.has_parent:
        return False
    if rule.require_parent and not input_.has_parent:
        return False
    return True


def classify(rules: List[HierarchyRule], input_: EvaluationInput) -> bool:
    """First-match-wins evaluation. Rules must already be ordered and enabled."""
    for rule in rules:
        if matches(rule, input_):
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
        if matches(rule, inp):
            return not rule.is_container
    return False


def _first_match(
    rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool
) -> Optional[HierarchyRule]:
    """Первое подошедшее правило (first-match-wins) или None."""
    inp = EvaluationInput(
        project_key=project_key or "",
        issue_type=issue_type or "",
        has_parent=has_parent,
    )
    for rule in rules:
        if matches(rule, inp):
            return rule
    return None


def is_service_epic(
    rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool
) -> bool:
    """Служебный эпик: первое подошедшее правило — «только с родителем» и «не контейнер».

    Сейчас это авто-Discovery внутри RFA. Инициативой не считается, но в
    сценарий может пойти по галочке «В план» — его часы идут сверх родителя.
    """
    rule = _first_match(rules, project_key, issue_type, has_parent)
    return rule is not None and bool(rule.require_parent) and not rule.is_container


def is_planning_leaf(
    rules: List[HierarchyRule], project_key: str, issue_type: str, has_parent: bool
) -> bool:
    """Явный лист, который никогда не кандидат в сценарий (OS/PMD и т.п.).

    Служебные эпики сюда не входят: их участие решает галочка «В план».
    """
    rule = _first_match(rules, project_key, issue_type, has_parent)
    return rule is not None and not rule.is_container and not rule.require_parent
