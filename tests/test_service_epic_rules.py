"""Служебный эпик = первое подошедшее правило «только с родителем» и «не контейнер».

Прочие явные листья (OS/PMD) — «листья планирования»: никогда не кандидаты.
Служебный эпик листом планирования НЕ считается — его решает галочка «В план».
"""
from app.models.hierarchy_rule import HierarchyRule
from app.services.hierarchy_rules import is_planning_leaf, is_service_epic


def _rule(**kw) -> HierarchyRule:
    base = dict(
        priority=10, project_key=None, issue_type=None,
        require_no_parent=False, require_parent=False,
        is_container=True, is_enabled=True,
    )
    base.update(kw)
    return HierarchyRule(**base)


SERVICE = _rule(priority=5, project_key="RFA", issue_type="Эпик", require_parent=True, is_container=False)
RFA_CONTAINER = _rule(priority=10, project_key="RFA", is_container=True)
OS_LEAF = _rule(priority=100, project_key="OS", is_container=False)
RULES = [SERVICE, RFA_CONTAINER, OS_LEAF]


def test_epic_inside_rfa_is_service_epic_not_planning_leaf():
    assert is_service_epic(RULES, "RFA", "Эпик", True) is True
    assert is_planning_leaf(RULES, "RFA", "Эпик", True) is False


def test_root_rfa_epic_is_not_service_epic():
    # Без родителя правило «только с родителем» не подходит — срабатывает контейнер RFA.
    assert is_service_epic(RULES, "RFA", "Эпик", False) is False
    assert is_planning_leaf(RULES, "RFA", "Эпик", False) is False


def test_os_task_is_planning_leaf_not_service_epic():
    assert is_planning_leaf(RULES, "OS", "Задача", True) is True
    assert is_service_epic(RULES, "OS", "Задача", True) is False


def test_first_match_wins_container_rule_with_higher_priority():
    rules = [_rule(priority=1, project_key="RFA", issue_type="Эпик", is_container=True), SERVICE]
    assert is_service_epic(rules, "RFA", "Эпик", True) is False


def test_no_rule_matched_is_neither():
    assert is_service_epic([], "X", "Y", True) is False
    assert is_planning_leaf([], "X", "Y", True) is False
