"""Tests for scenario team/external_qa_hours fields and rules endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    MandatoryWorkType,
    PlanningScenario,
    RoleCapacityRule,
    ScenarioRule,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def work_type(db_session):
    """Единственный тип обязательных работ для тестов."""
    wt = MandatoryWorkType(code="tech_debt", label="Технический долг", is_active=True)
    db_session.add(wt)
    db_session.commit()
    return wt


def _create_scenario(client, **kwargs):
    payload = {"name": "Test scenario", "year": 2026, "quarter": 1}
    payload.update(kwargs)
    r = client.post("/api/v1/planning/scenarios", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# test_scenario_create_copies_template_rules
# ---------------------------------------------------------------------------

def test_scenario_create_copies_template_rules(client, db_session, work_type):
    """POST /scenarios должен скопировать role_capacity_rules для year+quarter."""
    # Создать два правила-шаблона для Q1 2026.
    db_session.add(
        RoleCapacityRule(
            year=2026, quarter=1, role="analyst",
            work_type_id=work_type.id, percent_of_norm=20.0,
        )
    )
    db_session.add(
        RoleCapacityRule(
            year=2026, quarter=1, role=None,  # fallback
            work_type_id=work_type.id, percent_of_norm=10.0,
        )
    )
    # Правило для другого квартала — не должно попасть в копию.
    db_session.add(
        RoleCapacityRule(
            year=2026, quarter=2, role="analyst",
            work_type_id=work_type.id, percent_of_norm=15.0,
        )
    )
    db_session.commit()

    scenario = _create_scenario(client, year=2026, quarter=1)

    r = client.get(f"/api/v1/planning/scenarios/{scenario['id']}/rules")
    assert r.status_code == 200, r.text
    rules = r.json()

    # Только два правила Q1 2026 скопированы.
    assert len(rules) == 2
    percents = {(rule["role"], rule["percent_of_norm"]) for rule in rules}
    assert ("analyst", 20.0) in percents
    assert (None, 10.0) in percents
    # work_type_id совпадает.
    for rule in rules:
        assert rule["work_type_id"] == work_type.id


# ---------------------------------------------------------------------------
# test_put_scenario_rules_replaces
# ---------------------------------------------------------------------------

def test_put_scenario_rules_replaces(client, db_session, work_type):
    """PUT /scenarios/{id}/rules атомарно заменяет набор правил."""
    scenario = _create_scenario(client)
    sid = scenario["id"]

    # Первый PUT: 2 правила.
    r = client.put(
        f"/api/v1/planning/scenarios/{sid}/rules",
        json={
            "rules": [
                {"role": "analyst", "work_type_id": work_type.id, "percent_of_norm": 30.0},
                {"role": "dev", "work_type_id": work_type.id, "percent_of_norm": 20.0},
            ]
        },
    )
    assert r.status_code == 200, r.text
    rules = r.json()
    assert len(rules) == 2

    # GET подтверждает те же 2 правила.
    r2 = client.get(f"/api/v1/planning/scenarios/{sid}/rules")
    assert r2.status_code == 200
    assert len(r2.json()) == 2

    # Второй PUT: другой набор из 1 правила.
    r3 = client.put(
        f"/api/v1/planning/scenarios/{sid}/rules",
        json={
            "rules": [
                {"role": None, "work_type_id": work_type.id, "percent_of_norm": 5.0},
            ]
        },
    )
    assert r3.status_code == 200, r3.text
    new_rules = r3.json()
    assert len(new_rules) == 1
    assert new_rules[0]["role"] is None
    assert new_rules[0]["percent_of_norm"] == 5.0

    # GET подтверждает только новый набор.
    r4 = client.get(f"/api/v1/planning/scenarios/{sid}/rules")
    assert len(r4.json()) == 1


# ---------------------------------------------------------------------------
# test_patch_scenario_team_and_qa
# ---------------------------------------------------------------------------

def test_patch_scenario_team_and_qa(client, db_session):
    """PATCH /scenarios/{id} обновляет team и external_qa_hours независимо."""
    scenario = _create_scenario(client)
    sid = scenario["id"]
    assert scenario["team"] is None
    assert scenario["external_qa_hours"] is None

    # Задать обе поля.
    r = client.patch(
        f"/api/v1/planning/scenarios/{sid}",
        json={"team": "TeamA", "external_qa_hours": 200.0},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["team"] == "TeamA"
    assert body["external_qa_hours"] == 200.0

    # Патч только team — external_qa_hours должен сохраниться.
    r2 = client.patch(
        f"/api/v1/planning/scenarios/{sid}",
        json={"team": "TeamB"},
    )
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["team"] == "TeamB"
    assert body2["external_qa_hours"] == 200.0  # не сбросился

    # GET подтверждает итоговое состояние.
    r3 = client.get(f"/api/v1/planning/scenarios/{sid}")
    assert r3.status_code == 200
    body3 = r3.json()
    assert body3["team"] == "TeamB"
    assert body3["external_qa_hours"] == 200.0


# ---------------------------------------------------------------------------
# test_create_scenario_with_team_and_qa_from_payload
# ---------------------------------------------------------------------------

def test_create_scenario_with_team_and_qa_from_payload(client, db_session):
    """POST /scenarios с team+external_qa_hours в теле сохраняет их в БД."""
    scenario = _create_scenario(
        client, team="TeamC", external_qa_hours=80.0
    )
    assert scenario["team"] == "TeamC"
    assert scenario["external_qa_hours"] == 80.0

    # GET подтверждает.
    r = client.get(f"/api/v1/planning/scenarios/{scenario['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["team"] == "TeamC"
    assert body["external_qa_hours"] == 80.0
