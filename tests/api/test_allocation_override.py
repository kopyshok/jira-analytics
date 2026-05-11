"""PATCH /api/v1/planning/scenarios/{sid}/allocations/{aid}/override."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import BacklogItem, PlanningScenario, ScenarioAllocation


@pytest.fixture
def db_session():
    """Local override: StaticPool, чтобы TestClient разделял соединение с тестом."""
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
        app.dependency_overrides.pop(get_db, None)


def _setup(db_session, status="draft"):
    sc = PlanningScenario(name="S", year=2026, quarter="Q2", status=status)
    db_session.add(sc); db_session.flush()
    bi = BacklogItem(title="X", estimate_analyst_hours=40, estimate_dev_hours=120)
    db_session.add(bi); db_session.flush()
    alloc = ScenarioAllocation(scenario_id=sc.id, backlog_item_id=bi.id, included_flag=True)
    db_session.add(alloc); db_session.commit()
    return sc, bi, alloc


def test_save_override_4_values(db_session, client):
    sc, bi, alloc = _setup(db_session)
    resp = client.patch(
        f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}/override",
        json={"analyst": 25, "dev": 80, "qa": 40, "opo": 20},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["override_estimate_analyst_hours"] == 25
    assert body["override_estimate_dev_hours"] == 80


def test_all_null_clears_override(db_session, client):
    sc, bi, alloc = _setup(db_session)
    alloc.override_estimate_analyst_hours = 10
    db_session.commit()
    resp = client.patch(
        f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}/override",
        json={"analyst": None, "dev": None, "qa": None, "opo": None},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["override_estimate_analyst_hours"] is None


def test_approved_scenario_blocks_409(db_session, client):
    sc, bi, alloc = _setup(db_session, status="approved")
    resp = client.patch(
        f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}/override",
        json={"analyst": 1, "dev": 1, "qa": 1, "opo": 1},
    )
    assert resp.status_code == 409


def test_404_when_allocation_in_other_scenario(db_session, client):
    sc, bi, alloc = _setup(db_session)
    sc2 = PlanningScenario(name="other", year=2026, quarter="Q3", status="draft")
    db_session.add(sc2); db_session.commit()
    resp = client.patch(
        f"/api/v1/planning/scenarios/{sc2.id}/allocations/{alloc.id}/override",
        json={"analyst": 1, "dev": 1, "qa": 1, "opo": 1},
    )
    assert resp.status_code == 404
