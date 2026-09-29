"""API истории распределения по группам и перевода между командами с группой."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services import subgroup_shares as ss

A, B = "g-a", "g-b"


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app), testclient_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed(db):
    db.add_all([
        Team(id="t1", name="T", has_subgroups=True),
        Team(id="t0", name="Old", has_subgroups=False),
    ])
    db.flush()
    db.add_all([
        TeamSubgroup(id=A, team_id="t1", name="Ломбард", sort_order=1),
        TeamSubgroup(id=B, team_id="t1", name="РФМ", sort_order=2),
        Employee(id="e1", jira_account_id="acc-1", display_name="Иванов", is_active=True),
    ])
    db.flush()
    db.add(EmployeeTeam(employee_id="e1", team="T", is_primary=True))
    db.commit()


def test_put_get_delete_record(client):
    tc, db = client
    _seed(db)
    r = tc.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None, "shares": [{"subgroup_id": A, "percent": 100}],
    })
    assert r.status_code == 200
    r = tc.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": "2026-11-15",
        "shares": [{"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40}],
    })
    assert r.json() == [
        {"valid_from": None, "shares": [{"subgroup_id": A, "percent": 100}]},
        {"valid_from": "2026-11-15", "shares": [
            {"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40},
        ]},
    ]
    assert tc.get("/api/v1/teams/employees/e1/subgroup-shares", params={"team": "T"}).json() == r.json()
    r = tc.delete(
        "/api/v1/teams/employees/e1/subgroup-shares",
        params={"team": "T", "valid_from": "2026-11-15"},
    )
    assert [x["valid_from"] for x in r.json()] == [None]


def test_put_rejects_bad_sum(client):
    tc, db = client
    _seed(db)
    r = tc.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None,
        "shares": [{"subgroup_id": A, "percent": 50}, {"subgroup_id": B, "percent": 40}],
    })
    assert r.status_code == 422


def test_delete_missing_record_is_404(client):
    tc, db = client
    _seed(db)
    r = tc.delete("/api/v1/teams/employees/e1/subgroup-shares", params={"team": "T"})
    assert r.status_code == 404


def test_transfer_into_divided_team_requires_group(client):
    tc, db = client
    _seed(db)
    db.add(EmployeeTeam(employee_id="e1", team="Old", is_primary=False))
    db.query(EmployeeTeam).filter_by(employee_id="e1", team="T").delete()
    db.commit()
    r = tc.post("/api/v1/employees/e1/teams/transfer", json={
        "from_team": "Old", "to_team": "T", "on": "2026-11-01",
    })
    assert r.status_code == 422
    r = tc.post("/api/v1/employees/e1/teams/transfer", json={
        "from_team": "Old", "to_team": "T", "on": "2026-11-01", "subgroup_id": B,
    })
    assert r.status_code == 200
    assert ss.load_team(db, "T")["e1"] == [ss.ShareRecord(date(2026, 11, 1), ((B, 100),))]


def test_team_items_carry_current_distribution(client):
    tc, db = client
    _seed(db)
    tc.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None,
        "shares": [{"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40}],
    })
    items = tc.get("/api/v1/employees/e1/teams").json()
    t = next(i for i in items if i["team"] == "T")
    assert t["subgroup_id"] is None
    assert t["subgroup_label"] == "Ломбард 60% · РФМ 40%"


def test_set_subgroup_rejects_team_without_division(client):
    tc, db = client
    _seed(db)
    r = tc.put(
        "/api/v1/teams/employees/e1/subgroup", json={"team": "Old", "subgroup_id": A}
    )
    assert r.status_code == 422


def test_set_subgroup_rejects_unknown_group(client):
    tc, db = client
    _seed(db)
    r = tc.put(
        "/api/v1/teams/employees/e1/subgroup",
        json={"team": "T", "subgroup_id": "missing"},
    )
    assert r.status_code == 422


def test_put_rejects_duplicate_group(client):
    tc, db = client
    _seed(db)
    r = tc.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None,
        "shares": [{"subgroup_id": A, "percent": 50}, {"subgroup_id": A, "percent": 50}],
    })
    assert r.status_code == 422


def test_list_employees_with_teams_carries_distribution(client):
    tc, db = client
    _seed(db)
    tc.put("/api/v1/teams/employees/e1/subgroup-shares", json={
        "team": "T", "valid_from": None,
        "shares": [{"subgroup_id": A, "percent": 60}, {"subgroup_id": B, "percent": 40}],
    })
    r = tc.get("/api/v1/employees", params={"with_teams": "true"})
    assert r.status_code == 200
    emp = next(e for e in r.json() if e["id"] == "e1")
    t = next(i for i in emp["teams"] if i["team"] == "T")
    assert t["subgroup_id"] is None
    assert t["subgroup_label"] == "Ломбард 60% · РФМ 40%"
