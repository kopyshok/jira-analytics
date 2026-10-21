"""«Диаграмма» у утверждённого сценария: сервер создаёт план и отдаёт его в списке.

Страница планирования ресурсов создаёт план сама, когда приходит со сценарием
в адресе. Отказ сервера здесь повторялся бы на странице, поэтому закрепляем,
что сам сервер такой запрос принимает.
"""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import PlanningScenario

BASE = "/api/v1/resource-planning/resource-plans"
TEAM = "Команда 1С (ERP - УУ)"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_plan_created_for_approved_scenario_and_listed(client, db_session):
    sc = PlanningScenario(name="Q2 2026 plan", year=2026, quarter="Q2", status="approved", team=TEAM)
    db_session.add(sc)
    db_session.commit()
    sc_id = sc.id

    resp = client.post(BASE, json={"scenario_id": sc_id, "team": TEAM, "quarter": "Q2", "year": 2026})
    assert resp.status_code == 201, resp.text
    plan_id = resp.json()["id"]

    listed = client.get(BASE, params={"teams": TEAM}).json()
    assert [p["id"] for p in listed if p["scenario_id"] == sc_id] == [plan_id]
