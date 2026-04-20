"""Tests for SyncService."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import Project
from app.services.sync_service import SyncService, SyncStats
from app.connectors.schemas import (
    JiraIssueFieldsSchema,
    JiraIssueSchema,
    JiraIssueTypeSchema,
    JiraProjectSchema,
    JiraStatusSchema,
    JiraUserSchema,
)


class TestSyncStats:
    """Tests for SyncStats."""
    
    def test_initial_stats(self):
        """Test that initial stats are zero."""
        stats = SyncStats()
        
        assert stats.projects_synced == 0
        assert stats.issues_synced == 0
        assert stats.worklogs_synced == 0
        assert stats.errors == []
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        stats = SyncStats()
        stats.started_at = datetime(2024, 1, 1, 10, 0, 0)
        stats.finished_at = datetime(2024, 1, 1, 10, 1, 30)
        
        assert stats.duration_seconds == 90.0
    
    def test_to_dict(self):
        """Test stats serialization."""
        stats = SyncStats()
        stats.projects_synced = 5
        stats.projects_created = 3
        stats.finish()
        
        result = stats.to_dict()
        
        assert result["projects"]["synced"] == 5
        assert result["projects"]["created"] == 3
        assert "duration_seconds" in result


class TestSyncServiceUpsert:
    """Tests for SyncService upsert methods."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()
    
    @pytest.fixture
    def mock_jira(self):
        """Create mock Jira client."""
        return AsyncMock()
    
    def test_upsert_project(self, mock_db, mock_jira):
        """Test project upsert from Jira data."""
        service = SyncService(mock_db, mock_jira)
        
        jira_project = JiraProjectSchema(
            id="10001",
            key="PRJ",
            name="Test Project",
            description="Description",
            projectTypeKey="software"
        )
        
        # Mock the repository
        service.project_repo = MagicMock()
        service.project_repo.upsert_by_field.return_value = (MagicMock(), True)
        
        project, created = service._upsert_project(jira_project)
        
        service.project_repo.upsert_by_field.assert_called_once()
        call_args = service.project_repo.upsert_by_field.call_args
        assert call_args[0][0] == "jira_project_id"
        assert call_args[0][1] == "10001"
    
    def test_ensure_employee(self, mock_db, mock_jira):
        """Test employee creation from Jira user."""
        service = SyncService(mock_db, mock_jira)
        
        jira_user = JiraUserSchema(
            accountId="user123",
            displayName="John Doe",
            emailAddress="john@example.com",
            active=True
        )
        
        # Mock the repository
        service.employee_repo = MagicMock()
        mock_employee = MagicMock()
        service.employee_repo.upsert_by_field.return_value = (mock_employee, True)
        
        employee = service._ensure_employee(jira_user)

        assert employee == mock_employee
        assert service.stats.employees_created == 1
        assert service.stats.employees_synced == 1


def _make_issue_schema(
    *,
    jira_id: str,
    key: str,
    project_key: str,
    project_id: str,
    parent_key: str | None = None,
    issue_type: str = "Task",
) -> JiraIssueSchema:
    """Собрать минимальную JiraIssueSchema для тестов sync_issues."""
    fields_data = {
        "summary": f"Issue {key}",
        "issuetype": JiraIssueTypeSchema(id="1", name=issue_type, subtask=issue_type == "Sub-task"),
        "status": JiraStatusSchema(id="1", name="Open"),
        "project": JiraProjectSchema(id=project_id, key=project_key, name=project_key),
    }
    if parent_key:
        fields_data["parent"] = {"key": parent_key}
    return JiraIssueSchema(
        id=jira_id,
        key=key,
        fields=JiraIssueFieldsSchema(**fields_data),
    )


def _make_issue_schema_with_extra(
    *,
    jira_id: str,
    key: str,
    project_key: str,
    project_id: str,
    extra_fields: dict,
    issue_type: str = "RFA",
) -> JiraIssueSchema:
    """JiraIssueSchema с произвольными customfield-значениями в ``_extra``."""
    fields_data = {
        "summary": f"Issue {key}",
        "issuetype": JiraIssueTypeSchema(id="1", name=issue_type, subtask=False),
        "status": JiraStatusSchema(id="1", name="Open"),
        "project": JiraProjectSchema(id=project_id, key=project_key, name=project_key),
    }
    fields_data.update(extra_fields)
    return JiraIssueSchema(
        id=jira_id,
        key=key,
        fields=JiraIssueFieldsSchema(**fields_data),
    )


class TestSyncIssuePlannedHoursExtraction:
    """Tests for extracting planned hours / impact / risk custom fields."""

    def test_upsert_issue_extracts_planned_hours_from_customfields(self, db_session):
        """Когда customfield IDs настроены в AppSetting, sync должен
        заполнить Issue.planned_*_hours, impact, risk из _extra."""
        from app.models import AppSetting, Project
        from app.services.sync_service import SyncService

        db_session.add(AppSetting(key="jira_planned_analyst_hours_field_id", value="customfield_12001"))
        db_session.add(AppSetting(key="jira_planned_dev_hours_field_id", value="customfield_12002"))
        db_session.add(AppSetting(key="jira_planned_qa_hours_field_id", value="customfield_12003"))
        db_session.add(AppSetting(key="jira_planned_opo_hours_field_id", value="customfield_12004"))
        db_session.add(AppSetting(key="jira_impact_field_id", value="customfield_12010"))
        db_session.add(AppSetting(key="jira_risk_field_id", value="customfield_12011"))
        proj = Project(jira_project_id="p1", key="RFA", name="RFA")
        db_session.add(proj)
        db_session.commit()

        svc = SyncService(db_session, jira_client=MagicMock())
        schema = _make_issue_schema_with_extra(
            jira_id="10001",
            key="RFA-123",
            project_key="RFA",
            project_id="p1",
            extra_fields={
                "customfield_12001": 40,
                "customfield_12002": "40",
                "customfield_12003": 20.5,
                "customfield_12004": 20,
                "customfield_12010": "Высокий",
                "customfield_12011": "Низкий",
            },
        )
        issue, _ = svc._upsert_issue(schema, project_id=proj.id)
        db_session.commit()

        # Re-query to get fresh values after commit.
        issue = svc.issue_repo.get_by_field("jira_issue_id", "10001")
        assert issue.planned_analyst_hours == 40.0
        assert issue.planned_dev_hours == 40.0
        assert issue.planned_qa_hours == 20.5
        assert issue.planned_opo_hours == 20.0
        assert issue.impact == "high"
        assert issue.risk == "low"

    def test_upsert_issue_skips_unset_customfields(self, db_session):
        """Если customfield ID не настроен в AppSetting, Issue.planned_* остаются NULL."""
        from app.models import Project
        from app.services.sync_service import SyncService

        proj = Project(jira_project_id="p2", key="RFA", name="RFA")
        db_session.add(proj)
        db_session.commit()

        svc = SyncService(db_session, jira_client=MagicMock())
        schema = _make_issue_schema_with_extra(
            jira_id="10002",
            key="RFA-124",
            project_key="RFA",
            project_id="p2",
            extra_fields={},  # no customfields present, no AppSetting configured
        )
        issue, _ = svc._upsert_issue(schema, project_id=proj.id)
        db_session.commit()

        issue = svc.issue_repo.get_by_field("jira_issue_id", "10002")
        assert issue.planned_analyst_hours is None
        assert issue.planned_dev_hours is None
        assert issue.planned_qa_hours is None
        assert issue.planned_opo_hours is None
        assert issue.impact is None
        assert issue.risk is None

    def test_upsert_issue_normalizes_level_values(self, db_session):
        """impact/risk приходит как dict {value: ...} из Jira — нужно извлечь и нормализовать."""
        from app.models import AppSetting, Project
        from app.services.sync_service import SyncService

        db_session.add(AppSetting(key="jira_impact_field_id", value="customfield_12010"))
        db_session.add(AppSetting(key="jira_risk_field_id", value="customfield_12011"))
        proj = Project(jira_project_id="p3", key="RFA", name="RFA")
        db_session.add(proj)
        db_session.commit()

        svc = SyncService(db_session, jira_client=MagicMock())
        schema = _make_issue_schema_with_extra(
            jira_id="10003",
            key="RFA-125",
            project_key="RFA",
            project_id="p3",
            extra_fields={
                "customfield_12010": {"value": "Medium", "id": "1"},
                "customfield_12011": {"value": "Средний", "id": "2"},
            },
        )
        svc._upsert_issue(schema, project_id=proj.id)
        db_session.commit()

        issue = svc.issue_repo.get_by_field("jira_issue_id", "10003")
        assert issue.impact == "medium"
        assert issue.risk == "medium"


class TestSyncIssuesParentLinking:
    """Regression tests for parent_id linking on out-of-order sync (Bug #3)."""

    @pytest.mark.asyncio
    async def test_subtask_before_parent_is_linked_after_second_pass(self, db_session):
        """Подзадача пришла раньше эпика — после sync_issues parent_id должен быть выставлен."""
        # Pre-create local project so _get_project_by_jira_id finds it.
        project = Project(
            jira_project_id="10001",
            key="PRJ",
            name="Project",
        )
        db_session.add(project)
        db_session.commit()

        # Jira returns subtask FIRST, then its parent epic.
        subtask = _make_issue_schema(
            jira_id="20001",
            key="PRJ-2",
            project_key="PRJ",
            project_id="10001",
            parent_key="PRJ-1",
            issue_type="Sub-task",
        )
        epic = _make_issue_schema(
            jira_id="20002",
            key="PRJ-1",
            project_key="PRJ",
            project_id="10001",
            issue_type="Epic",
        )

        mock_jira = MagicMock()

        async def fake_iter(project_keys, since):  # noqa: ARG001
            yield subtask
            yield epic

        mock_jira.get_issues_updated_since = fake_iter

        service = SyncService(db_session, mock_jira)
        await service.sync_issues(project_keys=["PRJ"], incremental=False)

        child = service.issue_repo.get_by_field("key", "PRJ-2")
        parent = service.issue_repo.get_by_field("key", "PRJ-1")
        assert parent is not None
        assert child is not None
        assert child.parent_id == parent.id
