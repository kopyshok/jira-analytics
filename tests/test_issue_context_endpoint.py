"""Tests for GET /issues/{issue_id}/context and GET /issues/{parent_id}/children."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project
from app.models.hierarchy_rule import HierarchyRule


def _seed_rules(db):
    rules = [
        HierarchyRule(priority=50, issue_type="Эпик", require_no_parent=False,
                      is_container=True, is_enabled=True),
        HierarchyRule(priority=50, issue_type="Epic", require_no_parent=False,
                      is_container=True, is_enabled=True),
    ]
    db.add_all(rules)
    db.flush()


@pytest.fixture
def client(db_session):
    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client_with_project(db_session, project):
    """Client pre-seeded with a project (so schema is fully initialised)."""
    def override():
        yield db_session

    app.dependency_overrides[get_db] = override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def project(db_session):
    p = Project(jira_project_id="10001", key="PROJ", name="Test", is_active=True)
    db_session.add(p)
    db_session.flush()
    return p


def _issue(db, project_id, jira_id, key, summary, itype="Task", parent_id=None):
    i = Issue(
        jira_issue_id=jira_id,
        key=key,
        summary=summary,
        issue_type=itype,
        status="Open",
        status_category="new",
        project_id=project_id,
        parent_id=parent_id,
        include_in_analysis=True,
    )
    db.add(i)
    db.flush()
    return i


class TestIssueContextHappyPath:
    def test_ancestors_and_children(self, client, db_session, project):
        root = _issue(db_session, project.id, "1", "PROJ-1", "Root")
        mid = _issue(db_session, project.id, "2", "PROJ-2", "Middle", parent_id=root.id)
        leaf = _issue(db_session, project.id, "3", "PROJ-3", "Leaf", parent_id=mid.id)

        resp = client.get(f"/api/v1/issues/{mid.id}/context")
        assert resp.status_code == 200
        data = resp.json()

        assert data["id"] == mid.id
        assert data["key"] == "PROJ-2"
        assert len(data["ancestors"]) == 1
        assert data["ancestors"][0]["key"] == "PROJ-1"
        assert len(data["children"]) == 1
        assert data["children"][0]["key"] == "PROJ-3"
        assert data["subtree_count"] == 2  # mid + leaf

    def test_siblings_total(self, client, db_session, project):
        parent = _issue(db_session, project.id, "10", "P-10", "Parent")
        c1 = _issue(db_session, project.id, "11", "P-11", "Child1", parent_id=parent.id)
        _issue(db_session, project.id, "12", "P-12", "Child2", parent_id=parent.id)
        _issue(db_session, project.id, "13", "P-13", "Child3", parent_id=parent.id)

        resp = client.get(f"/api/v1/issues/{c1.id}/context")
        assert resp.status_code == 200
        assert resp.json()["siblings_total"] == 3  # c1+c2+c3

    def test_subtree_count_deep(self, client, db_session, project):
        root = _issue(db_session, project.id, "20", "D-1", "Root")
        c1 = _issue(db_session, project.id, "21", "D-2", "Child1", parent_id=root.id)
        c2 = _issue(db_session, project.id, "22", "D-3", "Child2", parent_id=root.id)
        _issue(db_session, project.id, "23", "D-4", "GrandChild", parent_id=c1.id)

        resp = client.get(f"/api/v1/issues/{root.id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subtree_count"] == 4
        # child subtree_counts
        child_counts = {ch["key"]: ch["subtree_count"] for ch in data["children"]}
        assert child_counts["D-2"] == 2
        assert child_counts["D-3"] == 1


class TestIssueContextRootIssue:
    def test_root_has_no_ancestors(self, client, db_session, project):
        root = _issue(db_session, project.id, "30", "R-1", "Root")
        resp = client.get(f"/api/v1/issues/{root.id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ancestors"] == []
        assert data["siblings_total"] == 0

    def test_root_subtree_is_one_when_leaf(self, client, db_session, project):
        leaf = _issue(db_session, project.id, "31", "R-2", "Lonely")
        resp = client.get(f"/api/v1/issues/{leaf.id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["subtree_count"] == 1
        assert data["children"] == []


class TestIssueContextLeaf:
    def test_leaf_no_children(self, client, db_session, project):
        parent = _issue(db_session, project.id, "40", "L-1", "Parent")
        leaf = _issue(db_session, project.id, "41", "L-2", "Leaf", parent_id=parent.id)

        resp = client.get(f"/api/v1/issues/{leaf.id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["children"] == []
        assert data["subtree_count"] == 1


class TestIssueContextContainer:
    def test_epic_is_container(self, client, db_session, project):
        _seed_rules(db_session)
        epic = _issue(db_session, project.id, "50", "E-1", "Epic Issue", itype="Эпик")

        resp = client.get(f"/api/v1/issues/{epic.id}/context")
        assert resp.status_code == 200
        assert resp.json()["is_container"] is True

    def test_task_is_not_container(self, client, db_session, project):
        _seed_rules(db_session)
        task = _issue(db_session, project.id, "51", "T-1", "Task Issue", itype="Task")

        resp = client.get(f"/api/v1/issues/{task.id}/context")
        assert resp.status_code == 200
        assert resp.json()["is_container"] is False


class TestIssueContext404:
    def test_unknown_id_returns_404(self, client_with_project, db_session):
        resp = client_with_project.get("/api/v1/issues/nonexistent-uuid-xxx/context")
        assert resp.status_code == 404


class TestIssueContextCycleProtection:
    def test_self_parent_does_not_hang(self, client, db_session, project):
        """Задача-предок с parent_id = self.id — обход обрывается на защите от циклов."""
        issue = _issue(db_session, project.id, "60", "CY-1", "Cycle issue")
        # Искусственно создаём self-reference
        issue.parent_id = issue.id
        db_session.flush()

        resp = client.get(f"/api/v1/issues/{issue.id}/context")
        assert resp.status_code == 200
        # ancestors пустые (сразу обнаружен цикл — id уже в seen_ids)
        assert resp.json()["ancestors"] == []


class TestIssueContextDescriptionGoals:
    def test_description_and_goals_returned(self, client, db_session, project):
        """Endpoint exposes description and goals from Issue model."""
        issue = Issue(
            jira_issue_id="90",
            key="DG-1",
            summary="With desc",
            issue_type="Task",
            status="Open",
            status_category="new",
            project_id=project.id,
            include_in_analysis=True,
            description="Some long description text",
            goals="Goal A, Goal B",
        )
        db_session.add(issue)
        db_session.flush()

        resp = client.get(f"/api/v1/issues/{issue.id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] == "Some long description text"
        assert data["goals"] == "Goal A, Goal B"

    def test_null_description_and_goals(self, client, db_session, project):
        issue = _issue(db_session, project.id, "91", "DG-2", "No desc")
        resp = client.get(f"/api/v1/issues/{issue.id}/context")
        assert resp.status_code == 200
        data = resp.json()
        assert data["description"] is None
        assert data["goals"] is None


class TestIssueChildren:
    def test_returns_direct_children(self, client, db_session, project):
        parent = _issue(db_session, project.id, "70", "CH-1", "Parent")
        c1 = _issue(db_session, project.id, "71", "CH-2", "C1", parent_id=parent.id)
        c2 = _issue(db_session, project.id, "72", "CH-3", "C2", parent_id=parent.id)

        resp = client.get(f"/api/v1/issues/{parent.id}/children")
        assert resp.status_code == 200
        keys = {r["key"] for r in resp.json()}
        assert keys == {"CH-2", "CH-3"}

    def test_limit_param(self, client, db_session, project):
        parent = _issue(db_session, project.id, "80", "LM-1", "Parent")
        for i in range(5):
            _issue(db_session, project.id, f"81{i}", f"LM-{i+2}", f"Child {i}", parent_id=parent.id)

        resp = client.get(f"/api/v1/issues/{parent.id}/children?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_parent_not_found(self, client_with_project, db_session, project):
        resp = client_with_project.get("/api/v1/issues/not-a-real-id/children")
        assert resp.status_code == 404
