"""Archived backlog items must not be pulled into scenarios."""

import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


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


def _override(db):
    app.dependency_overrides[get_db] = lambda: db


def test_create_scenario_excludes_archived_items(db_session):
    from app.models import BacklogItem, ScenarioAllocation

    db_session.add(BacklogItem(id="pa-active", title="active"))
    db_session.add(BacklogItem(
        id="pa-arch", title="archived",
        archived_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/planning/scenarios",
            json={"name": "Q2 draft", "year": 2026, "quarter": 2},
        )
        assert r.status_code == 201, r.text
        scenario_id = r.json()["id"]
    finally:
        app.dependency_overrides.clear()

    allocs = (
        db_session.query(ScenarioAllocation)
        .filter(ScenarioAllocation.scenario_id == scenario_id)
        .all()
    )
    item_ids = {a.backlog_item_id for a in allocs}
    assert "pa-active" in item_ids
    assert "pa-arch" not in item_ids


def test_sync_backlog_excludes_archived_items(db_session):
    from app.models import BacklogItem, PlanningScenario, ScenarioAllocation

    # Pre-existing draft scenario with zero allocations.
    scenario = PlanningScenario(
        id="sc-pa", name="Q2", year=2026, quarter="Q2", status="draft",
    )
    db_session.add(scenario)
    db_session.add(BacklogItem(id="pa2-active", title="active2"))
    db_session.add(BacklogItem(
        id="pa2-arch", title="archived2",
        archived_at=datetime.now(timezone.utc),
    ))
    db_session.commit()

    _override(db_session)
    try:
        client = TestClient(app)
        r = client.post(f"/api/v1/planning/scenarios/{scenario.id}/sync-backlog")
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()

    allocs = (
        db_session.query(ScenarioAllocation)
        .filter(ScenarioAllocation.scenario_id == scenario.id)
        .all()
    )
    item_ids = {a.backlog_item_id for a in allocs}
    assert "pa2-active" in item_ids
    assert "pa2-arch" not in item_ids
