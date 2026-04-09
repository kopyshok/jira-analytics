"""Tests for SQLAlchemy models."""

from datetime import datetime

from app.models import Employee, Project, Issue, Worklog


class TestEmployeeModel:
    """Test Employee model."""

    def test_create_employee(self, db_session):
        """Test creating an employee."""
        employee = Employee(
            jira_account_id="test-account-123",
            display_name="Test User",
            email="test@example.com",
            is_active=True,
        )
        db_session.add(employee)
        db_session.flush()

        assert employee.id is not None
        assert employee.jira_account_id == "test-account-123"
        assert employee.display_name == "Test User"
        assert employee.is_active is True

    def test_employee_repr(self, db_session):
        """Test employee string representation."""
        employee = Employee(
            jira_account_id="repr-test",
            display_name="John Doe",
        )
        assert repr(employee) == "<Employee John Doe>"


class TestProjectModel:
    """Test Project model."""

    def test_create_project(self, db_session):
        """Test creating a project."""
        project = Project(
            jira_project_id="10001",
            key="TEST",
            name="Test Project",
            description="A test project",
        )
        db_session.add(project)
        db_session.flush()

        assert project.id is not None
        assert project.key == "TEST"


class TestWorklogModel:
    """Test Worklog model."""

    def test_create_worklog_with_relations(self, db_session):
        """Test creating worklog with employee and issue relations."""
        # Create employee
        employee = Employee(
            jira_account_id="emp-1",
            display_name="Developer",
        )
        db_session.add(employee)

        # Create project
        project = Project(
            jira_project_id="proj-1",
            key="DEV",
            name="Development",
        )
        db_session.add(project)
        db_session.flush()

        # Create issue
        issue = Issue(
            jira_issue_id="issue-1",
            key="DEV-1",
            summary="Test Issue",
            issue_type="Task",
            status="In Progress",
            project_id=project.id,
        )
        db_session.add(issue)
        db_session.flush()

        # Create worklog
        worklog = Worklog(
            jira_worklog_id="wl-1",
            started_at=datetime.now(),
            hours=2.5,
            time_spent_seconds=9000,
            comment_text="Working on the task",
            issue_id=issue.id,
            employee_id=employee.id,
        )
        db_session.add(worklog)
        db_session.flush()

        assert worklog.id is not None
        assert worklog.hours == 2.5
        assert worklog.issue == issue
        assert worklog.employee == employee
