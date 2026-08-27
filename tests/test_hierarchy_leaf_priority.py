"""Вердикт «лист или контейнер» одинаков для дерева и для бэклога.

Регресс: правило «проект OS — не контейнер» перебивало более приоритетное
«тип Эпик — контейнер», и OS-Эпики выпадали из бэклога и сценариев.
"""

from app.models.hierarchy_rule import HierarchyRule
from app.services.hierarchy_rules import EvaluationInput, classify, is_explicit_leaf


def _rules():
    return [
        HierarchyRule(priority=50, project_key=None, issue_type="Эпик",
                      require_no_parent=False, is_container=True, is_enabled=True),
        HierarchyRule(priority=100, project_key="OS", issue_type=None,
                      require_no_parent=False, is_container=False, is_enabled=True),
    ]


def _both(project_key: str, issue_type: str, has_parent: bool = True):
    rules = _rules()
    leaf = is_explicit_leaf(rules, project_key=project_key, issue_type=issue_type,
                            has_parent=has_parent)
    container = classify(rules, EvaluationInput(project_key=project_key,
                                                issue_type=issue_type,
                                                has_parent=has_parent))
    return leaf, container


def test_os_epic_is_container_not_leaf():
    leaf, container = _both("OS", "Эпик")
    assert container is True
    assert leaf is False


def test_os_plain_task_stays_leaf():
    leaf, container = _both("OS", "Задача")
    assert container is False
    assert leaf is True


def test_unknown_project_defaults_to_visible():
    leaf, container = _both("RFA", "Инициатива (Финансы)")
    assert container is False
    assert leaf is False
