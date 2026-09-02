"""Unit tests for hierarchy rule evaluator."""


from app.models.hierarchy_rule import HierarchyRule
from app.services.hierarchy_rules import EvaluationInput, classify, is_explicit_leaf


def _rule(**kwargs):
    """Build an in-memory HierarchyRule with sane defaults."""
    defaults = dict(
        id="r", priority=100, project_key=None, issue_type=None,
        require_no_parent=False, require_parent=False, is_container=True, is_enabled=True,
        description=None,
    )
    defaults.update(kwargs)
    return HierarchyRule(**defaults)


class TestClassify:
    def test_empty_rules_returns_false(self):
        assert classify([], EvaluationInput("ITL", "Task", False)) is False

    def test_first_match_wins_by_order(self):
        rules = [
            _rule(priority=10, project_key="ITL", is_container=True),
            _rule(priority=20, project_key="ITL", is_container=False),
        ]
        assert classify(rules, EvaluationInput("ITL", "Task", False)) is True

    def test_project_wildcard_matches_any(self):
        rules = [_rule(project_key=None, issue_type="Epic", is_container=True)]
        assert classify(rules, EvaluationInput("ANY", "Epic", False)) is True

    def test_type_wildcard_matches_any(self):
        rules = [_rule(project_key="PRJ", issue_type=None, is_container=True)]
        assert classify(rules, EvaluationInput("PRJ", "Task", False)) is True

    def test_require_no_parent_skips_when_has_parent(self):
        rules = [_rule(project_key="ITL", require_no_parent=True, is_container=True)]
        assert classify(rules, EvaluationInput("ITL", "Task", True)) is False

    def test_require_parent_skips_when_root(self):
        rules = [_rule(project_key="RFA", require_parent=True, is_container=False)]
        assert classify(rules, EvaluationInput("RFA", "Эпик", False)) is False

    def test_require_parent_matches_nested_issue(self):
        """Дочерний Эпик внутри RFA — лист (не инициатива), корневой — нет."""
        rules = [
            _rule(priority=5, project_key="RFA", issue_type="Эпик",
                  require_parent=True, is_container=False),
            _rule(priority=10, project_key="RFA", is_container=True),
        ]
        assert is_explicit_leaf(rules, "RFA", "Эпик", has_parent=True) is True
        assert is_explicit_leaf(rules, "RFA", "Эпик", has_parent=False) is False
        assert is_explicit_leaf(rules, "RFA", "Инициатива", has_parent=False) is False

    def test_require_no_parent_matches_when_no_parent(self):
        rules = [_rule(project_key="ITL", require_no_parent=True, is_container=True)]
        assert classify(rules, EvaluationInput("ITL", "Task", False)) is True

    def test_is_container_false_overrides_later_true(self):
        rules = [
            _rule(priority=10, project_key="ITL", issue_type="История", is_container=False),
            _rule(priority=50, issue_type="История", is_container=True),
        ]
        # ITL-История hits the explicit False first
        assert classify(rules, EvaluationInput("ITL", "История", False)) is False
        # PRJ-История falls through to the priority=50 True rule
        assert classify(rules, EvaluationInput("PRJ", "История", False)) is True

    def test_disabled_rules_are_skipped_by_loader(self):
        # classify does not filter by is_enabled — that's load_rules' job.
        # This documents the contract: classify assumes rules already enabled.
        pass
