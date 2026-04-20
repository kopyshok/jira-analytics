"""Tests for MappingService."""

from datetime import datetime

import pytest

from app.models import (
    BacklogItem,
    Category,
    CategoryMapping,
    CategoryOverride,
    Employee,
    Issue,
    Project,
    ScopeRoot,
    Worklog,
)
from app.services.categories import CategoryCode, MappingSource
from app.services.mapping_service import MappingService, MappingStats


@pytest.fixture
def project(db_session):
    project = Project(jira_project_id="p1", key="PRJ", name="Project")
    db_session.add(project)
    db_session.flush()
    return project


@pytest.fixture
def employee(db_session):
    employee = Employee(jira_account_id="acc-1", display_name="Dev One")
    db_session.add(employee)
    db_session.flush()
    return employee


def _issue(db_session, project, key, parent=None):
    issue = Issue(
        jira_issue_id=f"jid-{key}",
        key=key,
        summary=key,
        issue_type="Task",
        status="Open",
        project_id=project.id,
        parent_id=parent.id if parent else None,
    )
    db_session.add(issue)
    db_session.flush()
    return issue


def _worklog(db_session, issue, employee, comment, jid):
    worklog = Worklog(
        jira_worklog_id=jid,
        started_at=datetime(2026, 2, 1, 9, 0, 0),
        hours=2.0,
        time_spent_seconds=7200,
        comment_text=comment,
        issue_id=issue.id,
        employee_id=employee.id,
    )
    db_session.add(worklog)
    db_session.flush()
    return worklog


class TestMappingStats:
    def test_to_dict(self):
        stats = MappingStats()
        stats.issues_processed = 3
        stats.worklogs_processed = 7
        stats.mappings_created = 10
        stats.mappings_updated = 2
        stats.finish()

        result = stats.to_dict()

        assert result["issues_processed"] == 3
        assert result["worklogs_processed"] == 7
        assert result["mappings_created"] == 10
        assert result["mappings_updated"] == 2
        assert result["duration_seconds"] >= 0


class TestRecalculateIssues:
    def test_creates_mappings_and_updates_denormalized_category(
        self, db_session, project
    ):
        epic = _issue(db_session, project, "PRJ-EPIC")
        child = _issue(db_session, project, "PRJ-1", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.BUSINESS_ANALYSIS,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()

        service = MappingService(db_session)
        count = service.recalculate_issues()

        assert count == 2
        assert service.stats.issues_processed == 2
        assert service.stats.mappings_created == 2

        db_session.refresh(child)
        assert child.category == CategoryCode.BUSINESS_ANALYSIS

        mapping = (
            db_session.query(CategoryMapping)
            .filter(
                CategoryMapping.entity_type == "issue",
                CategoryMapping.entity_id == child.id,
            )
            .one()
        )
        assert mapping.category == CategoryCode.BUSINESS_ANALYSIS
        assert mapping.source_rule == MappingSource.SCOPE_ROOT

    def test_idempotent_recalculation(self, db_session, project):
        _issue(db_session, project, "PRJ-1")

        first = MappingService(db_session)
        first.recalculate_issues()
        created_first = first.stats.mappings_created

        second = MappingService(db_session)
        second.recalculate_issues()

        assert created_first == 1
        assert second.stats.mappings_created == 0
        assert second.stats.mappings_updated == 0

    def test_updates_mapping_when_rule_changes(self, db_session, project):
        epic = _issue(db_session, project, "PRJ-EPIC")
        child = _issue(db_session, project, "PRJ-1", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.SUPPORT_CONSULTATION,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()

        MappingService(db_session).recalculate_issues()

        db_session.add(
            CategoryOverride(
                jira_issue_key="PRJ-1",
                category_code=CategoryCode.TECH_DEBT,
            )
        )
        db_session.flush()

        service = MappingService(db_session)
        service.recalculate_issues()

        assert service.stats.mappings_updated >= 1

        db_session.refresh(child)
        assert child.category == CategoryCode.TECH_DEBT

        mapping = (
            db_session.query(CategoryMapping)
            .filter(
                CategoryMapping.entity_type == "issue",
                CategoryMapping.entity_id == child.id,
            )
            .one()
        )
        assert mapping.category == CategoryCode.TECH_DEBT
        assert mapping.source_rule == MappingSource.OVERRIDE


class TestRecalculateWorklogs:
    def test_quality_rule_for_empty_comment(
        self, db_session, project, employee
    ):
        issue = _issue(db_session, project, "PRJ-1")
        worklog = _worklog(db_session, issue, employee, "", "wl-1")

        service = MappingService(db_session)
        service.recalculate_worklogs()

        assert service.stats.worklogs_processed == 1
        mapping = (
            db_session.query(CategoryMapping)
            .filter(
                CategoryMapping.entity_type == "worklog",
                CategoryMapping.entity_id == worklog.id,
            )
            .one()
        )
        assert mapping.category == CategoryCode.UNFILLED_WORKLOG
        assert mapping.source_rule == MappingSource.QUALITY_RULE

    def test_worklog_inherits_issue_category(
        self, db_session, project, employee
    ):
        epic = _issue(db_session, project, "PRJ-EPIC")
        child = _issue(db_session, project, "PRJ-1", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.MEETINGS,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()
        worklog = _worklog(
            db_session, child, employee, "Daily standup notes", "wl-2"
        )

        service = MappingService(db_session)
        service.recalculate_worklogs()

        mapping = (
            db_session.query(CategoryMapping)
            .filter(
                CategoryMapping.entity_type == "worklog",
                CategoryMapping.entity_id == worklog.id,
            )
            .one()
        )
        assert mapping.category == CategoryCode.MEETINGS
        assert mapping.source_rule == MappingSource.SCOPE_ROOT


class TestBacklogSyncTrigger:
    def test_creates_backlog_item_when_issue_enters_backlog_category(
        self, db_session, project
    ):
        """recalculate_issues должен создать BacklogItem для задач,
        чья denormalized category обновилась до 'initiatives_rfa'."""
        db_session.add(
            Category(
                code="initiatives_rfa",
                label="Инициативы и RFA",
                color="#7F77DD",
                sort_order=22,
                is_system=True,
            )
        )
        issue = Issue(
            jira_issue_id="jid-IB-1",
            key="IB-1",
            summary="Initiative 1",
            issue_type="Task",
            status="Open",
            project_id=project.id,
            assigned_category="initiatives_rfa",
            planned_dev_hours=8.0,
        )
        db_session.add(issue)
        db_session.flush()

        # Pre-condition: BacklogItem ещё нет.
        assert (
            db_session.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0
        )

        MappingService(db_session).recalculate_issues()

        item = (
            db_session.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        )
        assert item is not None
        assert item.estimate_dev_hours == 8.0


class TestRecalculateAll:
    def test_full_cycle(self, db_session, project, employee):
        epic = _issue(db_session, project, "PRJ-EPIC")
        child = _issue(db_session, project, "PRJ-1", parent=epic)
        db_session.add(
            ScopeRoot(
                category_code=CategoryCode.TECH_DEBT,
                jira_issue_key="PRJ-EPIC",
                is_enabled=True,
            )
        )
        db_session.flush()
        _worklog(db_session, child, employee, "Refactored module", "wl-1")
        _worklog(db_session, child, employee, "", "wl-2")

        service = MappingService(db_session)
        stats = service.recalculate_all()

        assert stats.issues_processed == 2
        assert stats.worklogs_processed == 2
        assert stats.mappings_created == 4  # 2 issues + 2 worklogs
        assert stats.finished_at is not None
        assert stats.duration_seconds >= 0
