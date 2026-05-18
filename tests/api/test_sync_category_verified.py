"""Tests for category_verified assignment in _upsert_issue."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.issue import Issue
from app.models.project import Project
import app.models  # noqa: F401


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_sync_service(db):
    """Minimal SyncService initialisation for unit testing _upsert_issue indirectly."""
    from unittest.mock import MagicMock, AsyncMock
    from app.services.sync_service import SyncService
    svc = SyncService.__new__(SyncService)
    svc.db = db
    from app.repositories.base import BaseRepository
    from app.models.issue import Issue
    svc.issue_repo = BaseRepository(Issue, db)
    # Stub everything else the constructor touches
    svc.connector = MagicMock()
    svc.project_repo = MagicMock()
    svc.worklog_repo = MagicMock()
    svc.employee_repo = MagicMock()
    svc._settings_cache = {}
    return svc


def _jira_issue(jira_id: str, key: str):
    from unittest.mock import MagicMock
    ji = MagicMock()
    ji.id = jira_id
    ji.key = key
    ji.fields.summary = "Test"
    ji.fields.description_text = None
    ji.fields.issuetype.name = "Task"
    ji.fields.status.name = "To Do"
    ji.fields.status.statusCategory = None
    ji.fields.priority = None
    ji.fields.statuscategorychangedate = None
    ji.fields.duedate = None
    ji.fields.assignee = None
    ji.fields._extra = {}
    return ji


def test_new_issue_no_parent_is_unverified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id=None)
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_new_issue_parent_verified_no_flag_is_still_unverified(db):
    """Все новые задачи попадают в стек на разбор независимо от родителя.

    `require_child_verification` на родителе — UI-подсказка при ручной
    верификации, не влияет на дефолт для новой задачи (sync_service.py:656).
    """
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    parent = Issue(
        id="par1", jira_issue_id="99", key="PRJ-99",
        summary="Parent", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=True, require_child_verification=False,
    )
    db.add(parent)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id="par1")
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_new_issue_parent_verified_with_flag_is_unverified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    parent = Issue(
        id="par1", jira_issue_id="99", key="PRJ-99",
        summary="Parent", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=True, require_child_verification=True,
    )
    db.add(parent)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id="par1")
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_new_issue_parent_unverified_is_unverified(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    parent = Issue(
        id="par1", jira_issue_id="99", key="PRJ-99",
        summary="Parent", issue_type="Epic", status="To Do",
        project_id="p1", category_verified=False, require_child_verification=False,
    )
    db.add(parent)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id="par1")
    db.flush()
    assert created is True
    assert issue.category_verified is False


def test_existing_issue_verified_flag_not_changed(db):
    db.add(Project(id="p1", jira_project_id="J1", key="PRJ", name="Project"))
    existing = Issue(
        id="ex1", jira_issue_id="100", key="PRJ-100",
        summary="Existing", issue_type="Task", status="To Do",
        project_id="p1", category_verified=True,
    )
    db.add(existing)
    db.commit()
    svc = _make_sync_service(db)
    issue, created = svc._upsert_issue(_jira_issue("100", "PRJ-100"), "p1", parent_id=None)
    db.flush()
    assert created is False
    assert issue.category_verified is True  # unchanged
