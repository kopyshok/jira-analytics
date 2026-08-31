"""Реестр команд и групп через API."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam


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
    emp = Employee(
        id="emp-tr-1", jira_account_id="jira-tr-1", display_name="Иванов", is_active=True
    )
    testclient_db_session.add(emp)
    testclient_db_session.add(
        EmployeeTeam(employee_id="emp-tr-1", team="Команда А", is_primary=True)
    )
    testclient_db_session.commit()
    return emp


def test_registry_lists_teams_with_groups(client, seeded):
    tc, _ = client

    resp = tc.get("/api/v1/teams/registry")

    assert resp.status_code == 200
    assert resp.json() == [
        {"name": "Команда А", "has_subgroups": False, "subgroups": []}
    ]


def test_enable_and_add_subgroup(client, seeded):
    tc, _ = client
    tc.get("/api/v1/teams/registry")

    resp = tc.patch("/api/v1/teams/registry/Команда А", json={"has_subgroups": True})
    assert resp.status_code == 200
    assert resp.json()["has_subgroups"] is True

    resp = tc.post(
        "/api/v1/teams/registry/Команда А/subgroups", json={"name": "Расчёты"}
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Расчёты"

    resp = tc.get("/api/v1/teams/registry")
    assert [g["name"] for g in resp.json()[0]["subgroups"]] == ["Расчёты"]


def test_add_subgroup_to_unknown_team_is_404(client, seeded):
    tc, _ = client

    resp = tc.post("/api/v1/teams/registry/Нет такой/subgroups", json={"name": "X"})

    assert resp.status_code == 404


def test_delete_subgroup_clears_employee_assignment(client, seeded):
    tc, db = client
    tc.get("/api/v1/teams/registry")
    tc.patch("/api/v1/teams/registry/Команда А", json={"has_subgroups": True})
    group_id = tc.post(
        "/api/v1/teams/registry/Команда А/subgroups", json={"name": "Расчёты"}
    ).json()["id"]

    resp = tc.put(
        "/api/v1/teams/employees/emp-tr-1/subgroup",
        json={"team": "Команда А", "subgroup_id": group_id},
    )
    assert resp.status_code == 204

    resp = tc.delete(f"/api/v1/teams/subgroups/{group_id}")
    assert resp.status_code == 204

    db.expire_all()
    row = db.query(EmployeeTeam).filter(EmployeeTeam.employee_id == "emp-tr-1").one()
    assert row.subgroup_id is None


def test_plain_team_list_unchanged(client, seeded):
    """Плоский список остаётся — на нём висит фильтр в шапке."""
    tc, _ = client

    resp = tc.get("/api/v1/teams")

    assert resp.status_code == 200
    assert resp.json() == ["Команда А"]
