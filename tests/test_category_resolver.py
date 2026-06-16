"""Tests for CategoryResolver service."""

from datetime import datetime

import pytest

from app.models import (
    CategoryOverride,
    Employee,
    Issue,
    Project,
    ScopeRoot,
    Worklog,
    WorklogQualityRule,
)
from app.services.categories import CategoryCode, MappingSource
from app.services.category_resolver import CategoryResolver


@pytest.fixture
def project(db_session):
    project = Project(
        jira_project_id="p1",
        key="PRJ",
        name="Project",
    )
    db_session.add(project)
    db_session.flush()
    return project


@pytest.fixture
def employee(db_session):
    employee = Employee(
        jira_account_id="acc-1",
        display_name="Dev One",
    )
    db_session.add(employee)
    db_session.flush()
    return employee


def _make_issue(db_session, project, key, parent=None):
    issue = Issue(
        jira_issue_id=f"jid-{key}",
        key=key,
        summary=f"Summary {key}",
        issue_type="Task",
        status="Open",
        project_id=project.id,
        parent_id=parent.id if parent else None,
    )
    db_session.add(issue)
    db_session.flush()
    return issue


class TestResolveForIssue:
    """Resolution priority: override -> scope_root -> fallback."""

    def test_explicit_override_wins(self, db_session, project):
        issue = _make_issue(db_session, project, "PRJ-1")
        db_session.add(
            CategoryOverride(
                jira_issue_key="PRJ-1",
                category_code=CategoryCode.TECH_DEBT,
            )
        )
        db_session.flush()

        result = CategoryResolver(db_session).resolve_for_issue(issue)

        assert result.category_code == CategoryCode.TECH_DEBT
        assert result.source == MappingSource.OVERRIDE
        assert result.source_entity_key == "PRJ-1"

    def test_scope_root_direct_match(self, db_session, project):
        epic = _make_issue(db_session, project, "PRJ-EPIC")
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.BUSINESS_ANALYSIS,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()

        result = CategoryResolver(db_session).resolve_for_issue(epic)

        assert result.category_code == CategoryCode.BUSINESS_ANALYSIS
        assert result.source == MappingSource.SCOPE_ROOT
        assert result.source_entity_key == "PRJ-EPIC"

    def test_scope_root_inherited_from_parent(self, db_session, project):
        epic = _make_issue(db_session, project, "PRJ-EPIC")
        child = _make_issue(db_session, project, "PRJ-2", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.SUPPORT_CONSULTATION,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()

        result = CategoryResolver(db_session).resolve_for_issue(child)

        assert result.category_code == CategoryCode.SUPPORT_CONSULTATION
        assert result.source == MappingSource.SCOPE_ROOT
        assert result.source_entity_key == "PRJ-EPIC"

    def test_override_on_intermediate_ancestor(self, db_session, project):
        epic = _make_issue(db_session, project, "PRJ-EPIC")
        mid = _make_issue(db_session, project, "PRJ-MID", parent=epic)
        leaf = _make_issue(db_session, project, "PRJ-LEAF", parent=mid)

        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.SUPPORT_CONSULTATION,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.add(
            CategoryOverride(
                jira_issue_key="PRJ-MID",
                category_code=CategoryCode.MEETINGS,
            )
        )
        db_session.flush()

        result = CategoryResolver(db_session).resolve_for_issue(leaf)

        assert result.category_code == CategoryCode.MEETINGS
        assert result.source == MappingSource.OVERRIDE
        assert result.source_entity_key == "PRJ-MID"

    def test_disabled_scope_root_ignored(self, db_session, project):
        epic = _make_issue(db_session, project, "PRJ-EPIC")
        child = _make_issue(db_session, project, "PRJ-2", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.BUSINESS_ANALYSIS,
                jira_issue_key="PRJ-EPIC",
                is_enabled=False,
            )
        )
        db_session.flush()

        result = CategoryResolver(db_session).resolve_for_issue(child)

        assert result.category_code == CategoryCode.UNFILLED_WORKLOG
        assert result.source == MappingSource.FALLBACK

    def test_fallback_when_no_rules(self, db_session, project):
        issue = _make_issue(db_session, project, "PRJ-LONE")

        result = CategoryResolver(db_session).resolve_for_issue(issue)

        assert result.category_code == CategoryCode.UNFILLED_WORKLOG
        assert result.source == MappingSource.FALLBACK


class TestResolveForWorklog:
    """Worklog resolution: quality rule first, then issue category."""

    def _make_worklog(self, db_session, issue, employee, comment_text):
        worklog = Worklog(
            jira_worklog_id=f"wl-{issue.key}-{comment_text or 'empty'}",
            started_at=datetime(2026, 1, 15, 10, 0, 0),
            hours=1.0,
            time_spent_seconds=3600,
            comment_text=comment_text,
            issue_id=issue.id,
            employee_id=employee.id,
        )
        db_session.add(worklog)
        db_session.flush()
        return worklog

    def test_empty_comment_triggers_quality_rule(
        self, db_session, project, employee
    ):
        issue = _make_issue(db_session, project, "PRJ-1")
        worklog = self._make_worklog(db_session, issue, employee, "")

        result = CategoryResolver(db_session).resolve_for_worklog(worklog)

        assert result.category_code == CategoryCode.UNFILLED_WORKLOG
        assert result.source == MappingSource.QUALITY_RULE

    def test_short_comment_triggers_quality_rule(
        self, db_session, project, employee
    ):
        issue = _make_issue(db_session, project, "PRJ-1")
        worklog = self._make_worklog(db_session, issue, employee, "ok")

        result = CategoryResolver(db_session).resolve_for_worklog(worklog)

        assert result.category_code == CategoryCode.UNFILLED_WORKLOG
        assert result.source == MappingSource.QUALITY_RULE

    def test_custom_min_comment_length_from_quality_rule(
        self, db_session, project, employee
    ):
        """Порог длины комментария берётся из worklog_quality_rules."""
        issue = _make_issue(db_session, project, "PRJ-1")
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.TECH_DEBT,
                jira_issue_key="PRJ-1",
                is_enabled=True,
            )
        )
        db_session.add(
            WorklogQualityRule(
                rule_code="min_comment_length",
                threshold_value=20.0,
                is_enabled=True,
            )
        )
        db_session.flush()

        # Комментарий длиной 10 символов — дефолт 5 бы пропустил, кастомный 20 — нет.
        worklog = self._make_worklog(db_session, issue, employee, "ten chars!")

        result = CategoryResolver(db_session).resolve_for_worklog(worklog)

        assert result.category_code == CategoryCode.UNFILLED_WORKLOG
        assert result.source == MappingSource.QUALITY_RULE

    def test_disabled_quality_rule_falls_back_to_default(
        self, db_session, project, employee
    ):
        """Выключенное правило → используется дефолт 5."""
        issue = _make_issue(db_session, project, "PRJ-1")
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.TECH_DEBT,
                jira_issue_key="PRJ-1",
                is_enabled=True,
            )
        )
        db_session.add(
            WorklogQualityRule(
                rule_code="min_comment_length",
                threshold_value=100.0,
                is_enabled=False,
            )
        )
        db_session.flush()

        worklog = self._make_worklog(
            db_session, issue, employee, "ten chars!"
        )

        result = CategoryResolver(db_session).resolve_for_worklog(worklog)

        assert result.category_code == CategoryCode.TECH_DEBT
        assert result.source == MappingSource.SCOPE_ROOT

    def test_good_comment_inherits_from_issue(
        self, db_session, project, employee
    ):
        epic = _make_issue(db_session, project, "PRJ-EPIC")
        child = _make_issue(db_session, project, "PRJ-2", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.TECH_DEBT,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()

        worklog = self._make_worklog(
            db_session, child, employee, "Fixed the migration bug"
        )

        result = CategoryResolver(db_session).resolve_for_worklog(worklog)

        assert result.category_code == CategoryCode.TECH_DEBT
        assert result.source == MappingSource.SCOPE_ROOT


def test_resolve_inherited_ignores_own_assigned(db_session):
    from app.models import Project, Issue
    from app.services.category_resolver import CategoryResolver

    project = Project(jira_project_id="p-inh", key="INH", name="Inh")
    db_session.add(project); db_session.flush()
    parent = Issue(jira_issue_id="j-par", key="INH-1", summary="par",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent); db_session.flush()
    child = Issue(jira_issue_id="j-ch", key="INH-2", summary="ch",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, assigned_category="meetings")
    db_session.add(child); db_session.flush()
    resolver = CategoryResolver(db_session)
    assert resolver.resolve_inherited_for_issue(child).category_code == "tech_debt"


def test_resolve_inherited_no_parent_is_fallback(db_session):
    from app.models import Project, Issue
    from app.services.category_resolver import CategoryResolver
    from app.services.categories import UNFILLED_WORKLOG_CODE

    project = Project(jira_project_id="p-nf", key="NF", name="NF")
    db_session.add(project); db_session.flush()
    orphan = Issue(jira_issue_id="j-or", key="NF-1", summary="or",
                   issue_type="Task", status="Open", project_id=project.id,
                   assigned_category="meetings")
    db_session.add(orphan); db_session.flush()
    resolver = CategoryResolver(db_session)
    assert resolver.resolve_inherited_for_issue(orphan).category_code == UNFILLED_WORKLOG_CODE


def test_reset_parent_context_sets_baseline_and_clears_flag(db_session):
    from app.models import Project, Issue
    from app.services.category_resolver import CategoryResolver, reset_parent_context

    project = Project(jira_project_id="p-rs", key="RS", name="RS")
    db_session.add(project); db_session.flush()
    parent = Issue(jira_issue_id="j-rsp", key="RS-1", summary="p",
                   issue_type="Epic", status="Open", project_id=project.id,
                   assigned_category="tech_debt")
    db_session.add(parent); db_session.flush()
    child = Issue(jira_issue_id="j-rsc", key="RS-2", summary="c",
                  issue_type="Task", status="Open", project_id=project.id,
                  parent_id=parent.id, parent_changed=True,
                  category_context="meetings", category_context_key="OLD-9")
    db_session.add(child); db_session.flush()
    resolver = CategoryResolver(db_session)
    reset_parent_context(db_session, child, resolver)
    assert child.parent_changed is False
    assert child.category_context == "tech_debt"
    assert child.category_context_key == "RS-1"
