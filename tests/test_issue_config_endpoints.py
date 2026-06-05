"""Issue-config endpoint tests — category assignment and include flag."""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project
from app.models.hierarchy_rule import HierarchyRule


def _seed_hierarchy_rules(db_session):
    """Insert the default hierarchy rules (migrations 014 + 015 seed).

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
        (50, None, 'Main box', False, True, 'Main box — всегда контейнер'),
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


def test_set_category_allowed_on_container_with_children(client, db_session):
    """Контейнер с детьми принимает категорию: дети наследуют через CategoryResolver."""
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80001", key="AD", name="Ad", is_active=True)
    db_session.add(project)
    db_session.flush()
    main_box = Issue(
        jira_issue_id="80001-1", key="AD-10",
        summary="Main box parent", issue_type="Main box", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add(main_box)
    db_session.flush()
    child = Issue(
        jira_issue_id="80001-2", key="AD-10-1",
        summary="Child", issue_type="Task", status="Open",
        project_id=project.id, parent_id=main_box.id, include_in_analysis=True,
    )
    db_session.add(child)
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{main_box.id}/category",
        json={"category_code": "development"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    assert db_session.get(Issue, main_box.id).assigned_category == "development"


def test_set_category_allowed_for_childless_container(client, db_session):
    """Контейнер без детей тоже принимает категорию."""
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80004", key="AD", name="Ad", is_active=True)
    db_session.add(project)
    db_session.flush()
    leaf_epic = Issue(
        jira_issue_id="80004-1", key="AD-14",
        summary="Childless epic", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add(leaf_epic)
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{leaf_epic.id}/category",
        json={"category_code": "development"},
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Issue, leaf_epic.id).assigned_category == "development"


def test_set_category_none_on_container_is_allowed(client, db_session):
    """Сброс категории (None) на контейнере не блокируется — нечего сбрасывать, но и ломать не надо."""
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80002", key="AD", name="Ad", is_active=True)
    db_session.add(project)
    db_session.flush()
    epic = Issue(
        jira_issue_id="80002-1", key="AD-11",
        summary="Epic", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add(epic)
    db_session.flush()

    response = client.put(
        f"/api/v1/issues/{epic.id}/category",
        json={"category_code": None},
    )
    assert response.status_code == 200


def test_batch_category_applies_to_containers_and_leaves(client, db_session):
    """Контейнеры и листья в батче получают категорию одинаково."""
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80003", key="AD", name="Ad", is_active=True)
    db_session.add(project)
    db_session.flush()
    container_with_kids = Issue(
        jira_issue_id="80003-1", key="AD-12",
        summary="Epic parent", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add(container_with_kids)
    db_session.flush()
    child = Issue(
        jira_issue_id="80003-1a", key="AD-12-1",
        summary="Child", issue_type="Task", status="Open",
        project_id=project.id, parent_id=container_with_kids.id, include_in_analysis=True,
    )
    leaf = Issue(
        jira_issue_id="80003-2", key="AD-13",
        summary="Leaf task", issue_type="Task", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add_all([child, leaf])
    db_session.flush()

    response = client.put(
        "/api/v1/issues/batch-category",
        json={
            "issue_ids": [container_with_kids.id, leaf.id],
            "category_code": "development",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2
    assert body["skipped_containers"] == []

    db_session.expire_all()
    assert db_session.get(Issue, container_with_kids.id).assigned_category == "development"
    assert db_session.get(Issue, leaf.id).assigned_category == "development"


def test_batch_category_cascades_to_descendants_without_own_category(client, db_session):
    """Назначение категории родителю каскадно протягивается на потомков
    без своей assigned_category; потомки с другой категорией не трогаются.
    """
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80010", key="CC", name="Cascade", is_active=True)
    db_session.add(project)
    db_session.flush()
    epic = Issue(
        jira_issue_id="80010-1", key="CC-1",
        summary="Epic parent", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add(epic)
    db_session.flush()
    blank_children = [
        Issue(
            jira_issue_id=f"80010-blank-{i}", key=f"CC-blank-{i}",
            summary=f"Blank child {i}", issue_type="Task", status="Open",
            project_id=project.id, parent_id=epic.id, include_in_analysis=True,
        ) for i in range(5)
    ]
    owned_children = [
        Issue(
            jira_issue_id=f"80010-owned-{i}", key=f"CC-owned-{i}",
            summary=f"Owned child {i}", issue_type="Task", status="Open",
            project_id=project.id, parent_id=epic.id,
            include_in_analysis=True,
            assigned_category="archive",
        ) for i in range(5)
    ]
    db_session.add_all(blank_children + owned_children)
    db_session.flush()

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": [epic.id], "category_code": "development", "verify": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 1
    assert sorted(body["cascaded_ids"]) == sorted([c.id for c in blank_children])
    assert body["archived_ids"] == []

    db_session.expire_all()
    assert db_session.get(Issue, epic.id).assigned_category == "development"
    for c in blank_children:
        persisted = db_session.get(Issue, c.id)
        assert persisted.assigned_category == "development"
        assert persisted.category_verified is True
    for c in owned_children:
        persisted = db_session.get(Issue, c.id)
        assert persisted.assigned_category == "archive"


def test_batch_category_cascade_stops_at_owned_descendant_subtree(client, db_session):
    """Каскад останавливается на потомке с собственной категорией —
    его поддерево не получает родительскую категорию.
    """
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80011", key="CB", name="Cascade boundary", is_active=True)
    db_session.add(project)
    db_session.flush()
    epic = Issue(
        jira_issue_id="80011-1", key="CB-1", summary="Epic",
        issue_type="Эпик", status="Open", project_id=project.id,
        include_in_analysis=True,
    )
    db_session.add(epic)
    db_session.flush()
    owned_mid = Issue(
        jira_issue_id="80011-2", key="CB-2", summary="Owned mid",
        issue_type="Task", status="Open", project_id=project.id,
        parent_id=epic.id, include_in_analysis=True,
        assigned_category="archive",
    )
    db_session.add(owned_mid)
    db_session.flush()
    grandchild = Issue(
        jira_issue_id="80011-3", key="CB-3", summary="Grandchild",
        issue_type="Task", status="Open", project_id=project.id,
        parent_id=owned_mid.id, include_in_analysis=True,
    )
    db_session.add(grandchild)
    db_session.flush()

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": [epic.id], "category_code": "development"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cascaded_ids"] == []

    db_session.expire_all()
    assert db_session.get(Issue, owned_mid.id).assigned_category == "archive"
    assert db_session.get(Issue, grandchild.id).assigned_category is None


def test_batch_category_cascade_propagates_archive_to_descendants(client, db_session):
    """Каскад с архивной категорией снимает include_in_analysis у потомков
    без своей категории и добавляет их в archived_ids.
    """
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80012", key="CA", name="Cascade arch", is_active=True)
    db_session.add(project)
    db_session.flush()
    epic = Issue(
        jira_issue_id="80012-1", key="CA-1", summary="Epic",
        issue_type="Эпик", status="Open", project_id=project.id,
        include_in_analysis=True,
    )
    db_session.add(epic)
    db_session.flush()
    child = Issue(
        jira_issue_id="80012-2", key="CA-2", summary="Child",
        issue_type="Task", status="Open", project_id=project.id,
        parent_id=epic.id, include_in_analysis=True,
    )
    db_session.add(child)
    db_session.flush()

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": [epic.id], "category_code": "archive"},
    )
    assert response.status_code == 200
    body = response.json()
    assert sorted(body["archived_ids"]) == sorted([epic.id, child.id])
    assert body["cascaded_ids"] == [child.id]

    db_session.expire_all()
    assert db_session.get(Issue, epic.id).include_in_analysis is False
    assert db_session.get(Issue, child.id).include_in_analysis is False


def test_tree_response_includes_is_container_flag(client, db_session):
    """IssueTreeNode.is_container = True для Эпика / Main box."""
    _seed_hierarchy_rules(db_session)
    project = Project(jira_project_id="80004", key="OS", name="OS", is_active=True)
    db_session.add(project)
    db_session.flush()
    epic = Issue(
        jira_issue_id="80004-1", key="OS-10",
        summary="Epic", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
    )
    db_session.add(epic)
    db_session.flush()
    child = Issue(
        jira_issue_id="80004-2", key="OS-11",
        summary="Child", issue_type="Task", status="Open",
        project_id=project.id, parent_id=epic.id, include_in_analysis=True,
    )
    db_session.add(child)
    db_session.flush()

    response = client.get("/api/v1/issues/tree?project_keys=OS")
    roots = response.json()
    assert len(roots) == 1
    assert roots[0]["key"] == "OS-10"
    assert roots[0]["is_container"] is True
    assert roots[0]["children"][0]["key"] == "OS-11"
    assert roots[0]["children"][0]["is_container"] is False


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


def test_batch_category_with_verify_flag_marks_verified(client, project_and_issues, db_session):
    """batch-category с verify=true помечает category_verified=True у всех ids."""
    _, issues = project_and_issues
    ids = [issues[0].id, issues[1].id]

    response = client.put(
        "/api/v1/issues/batch-category",
        json={
            "issue_ids": ids,
            "category_code": "development",
            "verify": True,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2

    for issue_id in ids:
        issue = db_session.get(Issue, issue_id)
        assert issue.assigned_category == "development"
        assert issue.category_verified is True


def test_batch_category_without_verify_flag_keeps_unverified(client, project_and_issues, db_session):
    """batch-category без verify не трогает category_verified."""
    _, issues = project_and_issues
    target = issues[0]
    target.category_verified = False
    db_session.flush()

    response = client.put(
        "/api/v1/issues/batch-category",
        json={"issue_ids": [target.id], "category_code": "development"},
    )

    assert response.status_code == 200
    db_session.expire_all()
    issue = db_session.get(Issue, target.id)
    assert issue.assigned_category == "development"
    assert issue.category_verified is False


def test_verify_with_category_code_applies_to_root(client, project_and_issues, db_session):
    """verify с has_category_code=True проставляет код на саму задачу + verified."""
    _, issues = project_and_issues
    target = issues[0]
    target.category_verified = False
    db_session.flush()

    response = client.post(
        f"/api/v1/issues/{target.id}/verify",
        json={
            "cascade": False,
            "require_child_verification": False,
            "has_category_code": True,
            "category_code": "development",
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    issue = db_session.get(Issue, target.id)
    assert issue.assigned_category == "development"
    assert issue.category_verified is True


def test_verify_cascade_applies_code_to_unverified_descendants_only(client, db_session):
    """verify cascade с category_code: невериф потомки получают код, вериф — не трогаются."""
    project = Project(jira_project_id="90001", key="VC", name="Verify cascade", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="90001-1", key="VC-1",
        summary="Parent", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
        category_verified=False,
    )
    db_session.add(parent)
    db_session.flush()

    unverified_kid = Issue(
        jira_issue_id="90001-2", key="VC-2",
        summary="Unverified kid", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        category_verified=False,
    )
    verified_kid = Issue(
        jira_issue_id="90001-3", key="VC-3",
        summary="Verified kid (own category)", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        category_verified=True, assigned_category="qa",
    )
    db_session.add_all([unverified_kid, verified_kid])
    db_session.flush()

    response = client.post(
        f"/api/v1/issues/{parent.id}/verify",
        json={
            "cascade": True,
            "require_child_verification": False,
            "has_category_code": True,
            "category_code": "development",
        },
    )

    assert response.status_code == 200
    db_session.expire_all()

    assert db_session.get(Issue, parent.id).assigned_category == "development"
    assert db_session.get(Issue, parent.id).category_verified is True

    assert db_session.get(Issue, unverified_kid.id).assigned_category == "development"
    assert db_session.get(Issue, unverified_kid.id).category_verified is True

    # Уже верифицированная задача с собственной категорией — не тронута
    assert db_session.get(Issue, verified_kid.id).assigned_category == "qa"
    assert db_session.get(Issue, verified_kid.id).category_verified is True


def test_verify_cascade_with_code_overrides_verified_descendants_without_own_category(client, db_session):
    """verify cascade с category_code: уже верифицированные потомки БЕЗ своей
    assigned_category получают код. Граница — только ручное решение PM
    (assigned_category != None). Регрессия для AD-4302-подобных случаев.
    """
    project = Project(jira_project_id="90100", key="VR", name="Verified regression", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="90100-1", key="VR-1",
        summary="Parent", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
        category_verified=False,
    )
    db_session.add(parent)
    db_session.flush()

    # Потомок — уже verified, но БЕЗ своей категории (типичный случай: после
    # старого MappingService / автоверификации). Должен подхватить родительскую.
    verified_blank = Issue(
        jira_issue_id="90100-2", key="VR-2",
        summary="Verified blank", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        category_verified=True, assigned_category=None,
    )
    db_session.add(verified_blank)
    db_session.flush()

    response = client.post(
        f"/api/v1/issues/{parent.id}/verify",
        json={
            "cascade": True,
            "require_child_verification": False,
            "has_category_code": True,
            "category_code": "development",
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(Issue, parent.id).assigned_category == "development"
    assert db_session.get(Issue, verified_blank.id).assigned_category == "development"


def test_verify_cascade_without_code_keeps_old_unverified_only_semantics(client, db_session):
    """verify cascade БЕЗ category_code: трогает только невериф потомков,
    верифицированных не трогает (старое поведение для проверочного каскада).
    """
    project = Project(jira_project_id="90200", key="VO", name="Verify only", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="90200-1", key="VO-1",
        summary="Parent", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
        category_verified=False, assigned_category="development",
    )
    db_session.add(parent)
    db_session.flush()

    verified_blank = Issue(
        jira_issue_id="90200-2", key="VO-2",
        summary="Verified blank", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        category_verified=True, assigned_category=None,
    )
    unverified_blank = Issue(
        jira_issue_id="90200-3", key="VO-3",
        summary="Unverified blank", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        category_verified=False, assigned_category=None,
    )
    db_session.add_all([verified_blank, unverified_blank])
    db_session.flush()

    response = client.post(
        f"/api/v1/issues/{parent.id}/verify",
        json={
            "cascade": True,
            "require_child_verification": False,
            "has_category_code": False,
            "category_code": None,
        },
    )

    assert response.status_code == 200
    db_session.expire_all()
    # Категории нигде не меняются
    assert db_session.get(Issue, verified_blank.id).assigned_category is None
    assert db_session.get(Issue, unverified_blank.id).assigned_category is None
    # Невериф подтверждён, ранее верифицированный не трогается (уже True)
    assert db_session.get(Issue, unverified_blank.id).category_verified is True
    assert db_session.get(Issue, verified_blank.id).category_verified is True


def test_tree_roots_marks_context_ancestor_for_tab(client, db_session):
    """Родитель без своей категории, но с потомком в архиве — is_context=true."""
    project = Project(jira_project_id="ctx-1", key="CTX", name="Context", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="ctx-1-1", key="CTX-1",
        summary="Parent w/o cat", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
        assigned_category=None, category_verified=True,
    )
    db_session.add(parent)
    db_session.flush()

    archived_kid = Issue(
        jira_issue_id="ctx-1-2", key="CTX-2",
        summary="Archived kid", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        assigned_category="archive", category="archive", category_verified=True,
    )
    db_session.add(archived_kid)
    db_session.flush()

    response = client.get("/api/v1/issues/tree/roots?project_keys=CTX&tab=archive")
    assert response.status_code == 200
    roots = response.json()
    keys = [r["key"] for r in roots]
    assert "CTX-1" in keys  # подтянут как контекст для архивного потомка
    parent_row = next(r for r in roots if r["key"] == "CTX-1")
    assert parent_row["is_context"] is True  # сам не матчит, помечен контекстом
    assert parent_row["descendant_match_count"] == 1


def test_tree_roots_self_match_not_marked_context(client, project_and_issues, db_session):
    """Сам матчит вкладку → is_context=false."""
    _, issues = project_and_issues
    target = issues[0]
    target.assigned_category = "archive"
    target.category = "archive"
    target.category_verified = True
    db_session.flush()

    response = client.get("/api/v1/issues/tree/roots?project_keys=TEST&tab=archive")
    assert response.status_code == 200
    roots = response.json()
    self_row = next(r for r in roots if r["id"] == target.id)
    assert self_row["is_context"] is False


def test_tree_roots_stack_categorized_parent_not_marked_context(client, db_session):
    """Разобранный родитель с неразобранными потомками на «К разбору» — НЕ context.

    Регрессия 90fd6d0: PM терял кнопку «Подтвердить N» у разобранного родителя
    на stack-вкладке — фронт рендерил его как read-only якорь. Контекст-метку
    оставляем только архив-вкладкам, где она и задумывалась.
    """
    project = Project(jira_project_id="stk-1", key="STK", name="Stack", is_active=True)
    db_session.add(project)
    db_session.flush()

    parent = Issue(
        jira_issue_id="stk-1-1", key="STK-1",
        summary="Categorized parent", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
        team="Team A",
        assigned_category="support_consultation",
        category="support_consultation",
        category_verified=True,
    )
    db_session.add(parent)
    db_session.flush()

    unsorted_kid = Issue(
        jira_issue_id="stk-1-2", key="STK-2",
        summary="Unsorted kid", issue_type="Task", status="Open",
        project_id=project.id, parent_id=parent.id, include_in_analysis=True,
        team="Team A",
        assigned_category=None, category=None, category_verified=False,
    )
    db_session.add(unsorted_kid)
    db_session.flush()

    response = client.get("/api/v1/issues/tree/roots?project_keys=STK&teams=Team A&tab=stack")
    assert response.status_code == 200
    roots = response.json()
    parent_row = next(r for r in roots if r["key"] == "STK-1")
    assert parent_row["is_context"] is False
    assert parent_row["descendant_match_count"] == 1
    assert parent_row["assigned_category"] == "support_consultation"


def test_children_stack_categorized_parent_not_marked_context(client, db_session):
    """То же для /issues/{id}/children?tab=stack — мост-родитель остаётся редактируемым."""
    project = Project(jira_project_id="stk-2", key="STC", name="Stack children", is_active=True)
    db_session.add(project)
    db_session.flush()

    root = Issue(
        jira_issue_id="stc-1", key="STC-1",
        summary="Root", issue_type="Эпик", status="Open",
        project_id=project.id, include_in_analysis=True,
        team="Team A",
        assigned_category="support_consultation",
        category_verified=True,
    )
    db_session.add(root)
    db_session.flush()

    bridge = Issue(
        jira_issue_id="stc-2", key="STC-2",
        summary="Categorized bridge", issue_type="Эпик", status="Open",
        project_id=project.id, parent_id=root.id, include_in_analysis=True,
        team="Team A",
        assigned_category="support_consultation",
        category_verified=True,
    )
    db_session.add(bridge)
    db_session.flush()

    leaf = Issue(
        jira_issue_id="stc-3", key="STC-3",
        summary="Unsorted leaf", issue_type="Task", status="Open",
        project_id=project.id, parent_id=bridge.id, include_in_analysis=True,
        team="Team A",
        assigned_category=None, category_verified=False,
    )
    db_session.add(leaf)
    db_session.flush()

    response = client.get(
        f"/api/v1/issues/{root.id}/children?teams=Team A&tab=stack"
    )
    assert response.status_code == 200
    rows = response.json()
    bridge_row = next(r for r in rows if r["key"] == "STC-2")
    assert bridge_row["is_context"] is False


def test_verify_without_category_code_keeps_existing_category(client, project_and_issues, db_session):
    """verify без has_category_code не меняет assigned_category — back-compat."""
    _, issues = project_and_issues
    target = issues[0]
    target.assigned_category = "qa"
    target.category_verified = False
    db_session.flush()

    response = client.post(
        f"/api/v1/issues/{target.id}/verify",
        json={"cascade": False, "require_child_verification": False},
    )

    assert response.status_code == 200
    db_session.expire_all()
    issue = db_session.get(Issue, target.id)
    assert issue.assigned_category == "qa"
    assert issue.category_verified is True
