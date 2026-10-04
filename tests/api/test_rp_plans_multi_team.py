"""Список планов принимает несколько команд шапки (через запятую)."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from tests.services.xteam_factory import make_plan

BASE = "/api/v1/resource-planning/resource-plans"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _teams(resp):
    return sorted(p["team"] for p in resp.json())


def test_teams_param_returns_plans_of_all_listed_teams(client, db_session):
    for t in ("A", "B", "C"):
        make_plan(db_session, t)
    db_session.commit()
    resp = client.get(BASE, params={"teams": "A,B"})
    assert resp.status_code == 200
    assert _teams(resp) == ["A", "B"]


def test_teams_param_tolerates_spaces_and_empty(client, db_session):
    for t in ("A", "B", "C"):
        make_plan(db_session, t)
    db_session.commit()
    assert _teams(client.get(BASE, params={"teams": " A , B "})) == ["A", "B"]
    assert _teams(client.get(BASE, params={"teams": ""})) == ["A", "B", "C"]
    assert _teams(client.get(BASE, params={"teams": " , "})) == ["A", "B", "C"]


def test_single_team_param_unchanged(client, db_session):
    for t in ("A", "B"):
        make_plan(db_session, t)
    db_session.commit()
    assert _teams(client.get(BASE, params={"team": "A"})) == ["A"]
    assert _teams(client.get(BASE)) == ["A", "B"]
