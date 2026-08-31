"""Подтверждение группы у задачи и сброс при переезде к другому родителю."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    Category,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    Team,
    TeamSubgroup,
)

TEAM = "Команда 1С (Бухгалтерия)"


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app), testclient_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def seeded(testclient_db_session):
    db = testclient_db_session
    db.add(Project(id="p1", jira_project_id="1", key="OS", name="OS"))
    team = Team(id="t-1", name=TEAM, has_subgroups=True)
    db.add(team)
    db.flush()
    db.add_all(
        [
            TeamSubgroup(id="sg-1", team_id="t-1", name="Расчёты", sort_order=1),
            TeamSubgroup(id="sg-2", team_id="t-1", name="Интеграции", sort_order=2),
        ]
    )
    emp = Employee(
        id="e-1", jira_account_id="acc-1", display_name="Иванов", is_active=True
    )
    db.add(emp)
    db.flush()
    db.add(
        EmployeeTeam(
            employee_id="e-1", team=TEAM, is_primary=True, subgroup_id="sg-2"
        )
    )
    issue = Issue(
        id="i-1",
        jira_issue_id="10001",
        key="OS-1",
        summary="x",
        issue_type="Task",
        status="Open",
        project_id="p1",
        team=TEAM,
        assignee_account_id="acc-1",
    )
    db.add(issue)
    db.commit()
    return issue


def test_confirm_subgroup_marks_verified(client, seeded):
    tc, db = client

    resp = tc.put("/api/v1/issues/i-1/subgroup", json={"subgroup_id": "sg-1"})

    assert resp.status_code == 200
    assert resp.json() == {
        "ok": True,
        "key": "OS-1",
        "subgroup_id": "sg-1",
        "source": "assigned",
        "verified": True,
    }
    db.expire_all()
    issue = db.get(Issue, "i-1")
    assert issue.assigned_subgroup_id == "sg-1"
    assert issue.subgroup_verified is True


def test_clearing_falls_back_to_guess(client, seeded):
    """Пустое значение возвращает задачу к предположению по исполнителю."""
    tc, db = client
    tc.put("/api/v1/issues/i-1/subgroup", json={"subgroup_id": "sg-1"})

    resp = tc.put("/api/v1/issues/i-1/subgroup", json={"subgroup_id": None})

    assert resp.status_code == 200
    assert resp.json()["subgroup_id"] == "sg-2"
    assert resp.json()["source"] == "guess"


def test_unknown_issue_is_404(client, seeded):
    tc, _ = client

    resp = tc.put("/api/v1/issues/нет/subgroup", json={"subgroup_id": "sg-1"})

    assert resp.status_code == 404


def test_parent_move_resets_subgroup_verification(testclient_db_session):
    """Переезд к другому родителю снимает подтверждение и категории, и группы."""
    db = testclient_db_session
    db.add(Project(id="p2", jira_project_id="2", key="OS2", name="OS2"))
    db.add_all(
        [
            Category(code="cat_a", label="A", is_system=False),
            Category(code="cat_b", label="B", is_system=False),
        ]
    )
    old_parent = Issue(
        id="p-old", jira_issue_id="20001", key="OS2-10", summary="old",
        issue_type="Epic", status="Open", project_id="p2", assigned_category="cat_a",
    )
    new_parent = Issue(
        id="p-new", jira_issue_id="20002", key="OS2-11", summary="new",
        issue_type="Epic", status="Open", project_id="p2", assigned_category="cat_b",
    )
    child = Issue(
        id="c-1", jira_issue_id="20003", key="OS2-12", summary="child",
        issue_type="Task", status="Open", project_id="p2", parent_id="p-old",
        category_verified=True, subgroup_verified=True,
        category_context="cat_a", category_context_key="OS2-10",
    )
    db.add_all([old_parent, new_parent, child])
    db.commit()

    child.parent_id = "p-new"
    db.commit()

    from app.services.mapping_service import MappingService

    MappingService(db).recalculate_issues()

    db.expire_all()
    moved = db.get(Issue, "c-1")
    assert moved.parent_changed is True
    assert moved.category_verified is False
    assert moved.subgroup_verified is False


def test_tree_roots_carry_resolved_subgroup(client, seeded):
    """Стопка разбора видит предположение по исполнителю."""
    tc, _ = client

    resp = tc.get("/api/v1/issues/tree/roots", params={"teams": TEAM})

    assert resp.status_code == 200
    node = next(n for n in resp.json() if n["key"] == "OS-1")
    assert node["subgroup_id"] == "sg-2"
    assert node["subgroup_name"] == "Интеграции"
    assert node["subgroup_source"] == "guess"
