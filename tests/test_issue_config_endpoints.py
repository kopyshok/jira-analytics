"""Issue-config endpoint tests — category assignment and include flag."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project
from app.models.hierarchy_rule import HierarchyRule


def _seed_hierarchy_rules(db_session):
    """Insert the 12 default hierarchy rules (same as migration 014 seed).

    Conftest wipes hierarchy_rule between tests, so any test that relies on
    classification behaviour must call this before issuing tree requests.
    Uses flush (not commit) to keep the connection open on the in-memory DB.
    """
    seeds = [
        (10, 'ITL', None, True, True, 'ITL без родителя — контейнер'),
        (10, 'RFA', None, False, True, 'RFA всегда контейнер'),
        (10, 'PRJ', None, False, True, 'PRJ всегда контейнер'),
        (50, None, 'Эпик', False, True, None),
        (50, None, 'Epic', False, True, None),
        (50, None, 'Инициатива', False, True, None),
        (50, None, 'Инициатива (E-com)', False, True, None),
        (50, None, 'Инициатива (Ритейл)', False, True, None),
        (50, None, 'Инициатива (Финансы)', False, True, None),
        (50, None, 'История', False, True, None),
        (50, None, 'Story', False, True, None),
        (50, None, 'Цель', False, True, None),
    ]
    for priority, project, itype, np, ic, desc in seeds:
        db_session.add(HierarchyRule(
            priority=priority, project_key=project, issue_type=itype,
            require_no_parent=np, is_container=ic, is_enabled=True,
            description=desc,
        ))
    db_session.flush()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def project_and_issues(db_session):
    project = Project(
        jira_project_id="10001",
        key="TEST",
        name="Test project",
        is_active=True,
    )
    db_session.add(project)
    db_session.flush()

    issues = [
        Issue(
            jira_issue_id=f"100{i}",
            key=f"TEST-{i}",
            summary=f"Issue {i}",
            issue_type="Task",
            status="Open",
            project_id=project.id,
            include_in_analysis=True,
        )
        for i in range(1, 4)
    ]
    db_session.add_all(issues)
    db_session.flush()
    return project, issues


def test_set_category_archive_auto_excludes(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "archive"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assigned_category"] == "archive"
    assert body["include_in_analysis"] is False
    assert body["auto_excluded"] is True

    db_session.expire_all()
    persisted = db_session.get(Issue, target.id)
    assert persisted.include_in_analysis is False


def test_set_category_non_archive_keeps_include(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "development"},
    )

    body = response.json()
    assert body["assigned_category"] == "development"
    assert body["include_in_analysis"] is True
    assert body["auto_excluded"] is False

    db_session.expire_all()
    persisted = db_session.get(Issue, target.id)
    assert persisted.include_in_analysis is True


def test_set_category_archive_already_excluded_does_not_re_report(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]
    target.include_in_analysis = False
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "archive"},
    )

    body = response.json()
    assert body["assigned_category"] == "archive"
    assert body["include_in_analysis"] is False
    assert body["auto_excluded"] is False


def test_set_category_to_none_leaves_include_alone(client, project_and_issues, db_session):
    _, issues = project_and_issues
    target = issues[0]
    target.assigned_category = "archive"
    target.include_in_analysis = False
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": None},
    )

    body = response.json()
    assert body["assigned_category"] is None
    assert body["include_in_analysis"] is False


def test_batch_category_archive_reports_archived_ids(client, project_and_issues, db_session):
    _, issues = project_and_issues
    ids = [issues[0].id, issues[1].id]

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": ids, "category_code": "archive"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2
    assert sorted(body["archived_ids"]) == sorted(ids)

    for issue_id in ids:
        issue = db_session.get(Issue, issue_id)
        assert issue.assigned_category == "archive"
        assert issue.include_in_analysis is False


def test_set_category_archive_target_also_auto_excludes(client, project_and_issues, db_session):
    """archive_target — вторая архив-категория, ведёт себя как archive."""
    _, issues = project_and_issues
    target = issues[0]

    response = client.put(
        f"/api/v1/issues/{target.id}/category",
        json={"category_code": "archive_target"},
    )
    body = response.json()
    assert body["assigned_category"] == "archive_target"
    assert body["include_in_analysis"] is False
    assert body["auto_excluded"] is True


def test_batch_category_archive_target_reports_archived_ids(client, project_and_issues, db_session):
    _, issues = project_and_issues
    ids = [issues[0].id, issues[1].id]

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": ids, "category_code": "archive_target"},
    )
    body = response.json()
    assert body["updated"] == 2
    assert sorted(body["archived_ids"]) == sorted(ids)


def test_batch_category_non_archive_returns_empty_archived_ids(client, project_and_issues):
    _, issues = project_and_issues

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": [issues[0].id], "category_code": "development"},
    )

    body = response.json()
    assert body["updated"] == 1
    assert body["archived_ids"] == []


def test_tree_pulls_in_ancestor_of_different_team_as_context(client, db_session):
    """Родитель с другой командой дотаскивается как context (AD-357 сценарий)."""
    project = Project(jira_project_id="20001", key="AD", name="Ad project", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="50001",
        key="AD-227",
        summary="Epic in team A",
        issue_type="Epic",
        status="Open",
        project_id=project.id,
        team="Team A",
        include_in_analysis=True,
    )
    db_session.add(parent)
    db_session.flush()

    child = Issue(
        jira_issue_id="50002",
        key="AD-357",
        summary="Subtask in team B",
        issue_type="Task",
        status="Open",
        project_id=project.id,
        parent_id=parent.id,
        team="Team B",
        include_in_analysis=True,
    )
    db_session.add(child)
    db_session.flush()

    response = client.get("/api/v1/issues/tree?project_keys=AD&teams=Team B")
    assert response.status_code == 200
    roots = response.json()

    # AD-227 should appear at root as context (since AD-357 matches and needs parent)
    assert len(roots) == 1, roots
    root = roots[0]
    assert root["key"] == "AD-227"
    assert root["is_context"] is True
    assert len(root["children"]) == 1
    leaf = root["children"][0]
    assert leaf["key"] == "AD-357"
    assert leaf["is_context"] is False


def test_tree_groups_childless_non_epic_roots_into_operations(client, db_session):
    """Bare «Задача» без parent и без детей уходит в __operations__."""
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="30001", key="AD", name="Ad project", is_active=True)
    db_session.add(project)
    db_session.flush()

    db_session.add_all([
        Issue(
            jira_issue_id="70001", key="AD-1",
            summary="Standalone ops task",
            issue_type="Задача", status="Готово",
            project_id=project.id, include_in_analysis=True,
        ),
        Issue(
            jira_issue_id="70002", key="AD-2",
            summary="Empty epic", issue_type="Эпик", status="Open",
            project_id=project.id, include_in_analysis=True,
        ),
    ])
    db_session.flush()

    response = client.get("/api/v1/issues/tree?project_keys=AD")
    roots = response.json()
    keys = [r["key"] or r["id"] for r in roots]
    assert "AD-2" in keys
    # Operations group should appear with AD-1 inside
    ops = next((r for r in roots if r["id"] == "__operations__"), None)
    assert ops is not None, roots
    assert ops["issue_type"] == "group"
    inside = [c["key"] for c in ops["children"]]
    assert inside == ["AD-1"]
    # AD-1 must NOT appear as standalone root
    assert "AD-1" not in keys


def test_tree_without_filter_does_not_flag_context(client, db_session):
    project = Project(jira_project_id="20002", key="AD", name="Ad project", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="60001",
        key="AD-1",
        summary="Epic",
        issue_type="Epic",
        status="Open",
        project_id=project.id,
        team="Team A",
        include_in_analysis=True,
    )
    db_session.add(parent)
    db_session.flush()

    child = Issue(
        jira_issue_id="60002",
        key="AD-2",
        summary="Child",
        issue_type="Task",
        status="Open",
        project_id=project.id,
        parent_id=parent.id,
        team="Team A",
        include_in_analysis=True,
    )
    db_session.add(child)
    db_session.flush()

    response = client.get("/api/v1/issues/tree?project_keys=AD")
    roots = response.json()
    assert len(roots) == 1
    assert roots[0]["key"] == "AD-1"
    assert roots[0]["is_context"] is False
    assert roots[0]["children"][0]["is_context"] is False


class TestTreeWithHierarchyRules:
    def _seed_rules(self, db_session):
        """Re-seed the 12 default hierarchy rules that migration 014 installs.

        Conftest wipes hierarchy_rule between tests, so these tests insert
        the exact seed set from migration 014 before asserting.
        """
        _seed_hierarchy_rules(db_session)

    def _make_client(self, db_session):
        """Return a TestClient that shares db_session with the test."""
        def override_get_db():
            yield db_session

        app.dependency_overrides[get_db] = override_get_db
        return TestClient(app)

    def _make_issue(self, db_session, project, key, issue_type, parent=None):
        issue = Issue(
            jira_issue_id=f"jid-{key}",
            key=key,
            summary=key,
            issue_type=issue_type,
            status="В работе",
            project_id=project.id,
            parent_id=parent.id if parent else None,
            synced_at=datetime.utcnow(),
        )
        db_session.add(issue)
        db_session.flush()
        return issue

    def test_itl_root_no_parent_stays_as_root_via_seed(self, db_session):
        self._seed_rules(db_session)
        proj = Project(jira_project_id="p-itl", key="ITL", name="ITL")
        db_session.add(proj)
        db_session.flush()
        self._make_issue(db_session, proj, "ITL-1", "Задача")
        db_session.flush()

        c = self._make_client(db_session)
        resp = c.get("/api/v1/issues/tree?project_keys=ITL")
        data = resp.json()

        root_keys = [n["key"] for n in data]
        assert "ITL-1" in root_keys
        ops = next((n for n in data if n["id"] == "__operations__"), None)
        if ops is not None:
            assert not any(c_node["key"] == "ITL-1" for c_node in ops["children"])

    def test_leaf_root_without_matching_rule_goes_to_operations(self, db_session):
        self._seed_rules(db_session)
        proj = Project(jira_project_id="p-os", key="OS", name="OS")
        db_session.add(proj)
        db_session.flush()
        self._make_issue(db_session, proj, "OS-1", "Задача")
        db_session.flush()

        c = self._make_client(db_session)
        resp = c.get("/api/v1/issues/tree?project_keys=OS")
        data = resp.json()

        root_keys = [n["key"] for n in data]
        assert "OS-1" not in root_keys
        ops = next(n for n in data if n["id"] == "__operations__")
        assert any(c_node["key"] == "OS-1" for c_node in ops["children"])

    def test_disabled_rule_not_applied(self, db_session):
        self._seed_rules(db_session)
        # Disable the ITL seed rule; ITL leaf now collapses into operations.
        db_session.query(HierarchyRule).filter(
            HierarchyRule.project_key == "ITL"
        ).update({"is_enabled": False})
        db_session.flush()

        proj = Project(jira_project_id="p-itl2", key="ITL", name="ITL")
        db_session.add(proj)
        db_session.flush()
        self._make_issue(db_session, proj, "ITL-2", "Задача")
        db_session.flush()

        c = self._make_client(db_session)
        resp = c.get("/api/v1/issues/tree?project_keys=ITL")
        data = resp.json()
        ops = next(n for n in data if n["id"] == "__operations__")
        assert any(c_node["key"] == "ITL-2" for c_node in ops["children"])
