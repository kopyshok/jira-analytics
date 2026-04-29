"""Tests for GET /scenarios/{sid}/revisions/{rid}/breakdown endpoint."""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    PlanningScenario,
    ScenarioAllocation,
    ScenarioAllocationBreakdownSnapshot,
    ScenarioRevision,
)


def _uid() -> str:
    return str(uuid.uuid4())


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


def _make_scenario(db, team="TeamA", year=2026, quarter="Q2", status="approved"):
    s = PlanningScenario(
        id=_uid(), name="Test", year=year, quarter=quarter,
        status=status, team=team,
    )
    db.add(s)
    db.flush()
    return s


def _make_revision(db, scenario_id, algo_version="v2"):
    rev = ScenarioRevision(
        id=_uid(),
        scenario_id=scenario_id,
        revision_number=1,
        approved_at=datetime.utcnow(),
        algo_version=algo_version,
    )
    db.add(rev)
    db.flush()
    return rev


def _make_backlog_item(db):
    bi = BacklogItem(id=_uid(), title="Initiative A")
    db.add(bi)
    db.flush()
    return bi


def _make_allocation(db, scenario_id, backlog_item_id):
    alloc = ScenarioAllocation(
        id=_uid(),
        scenario_id=scenario_id,
        backlog_item_id=backlog_item_id,
        included_flag=True,
        planned_hours=30.0,
    )
    db.add(alloc)
    db.flush()
    return alloc


def _make_breakdown_row(db, revision_id, allocation_id, month, role="analyst", hours=10.0):
    row = ScenarioAllocationBreakdownSnapshot(
        id=_uid(),
        revision_id=revision_id,
        allocation_id=allocation_id,
        month=month,
        role=role,
        employee_id=None,
        is_external=False,
        hours=hours,
    )
    db.add(row)
    db.flush()
    return row


class TestBreakdownEndpoint:
    def test_breakdown_endpoint_returns_rows(self, client, db_session):
        scenario = _make_scenario(db_session)
        rev = _make_revision(db_session, scenario.id, algo_version="v2")
        bi = _make_backlog_item(db_session)
        alloc = _make_allocation(db_session, scenario.id, bi.id)
        _make_breakdown_row(db_session, rev.id, alloc.id, month=4, hours=10.0)
        _make_breakdown_row(db_session, rev.id, alloc.id, month=5, hours=10.0)
        db_session.commit()

        resp = client.get(
            f"/api/v1/planning/scenarios/{scenario.id}/revisions/{rev.id}/breakdown"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["revision_id"] == rev.id
        assert data["algo_version"] == "v2"
        rows = data["rows"]
        assert len(rows) == 2
        allocation_ids = {r["allocation_id"] for r in rows}
        assert allocation_ids == {alloc.id}
        months = {r["month"] for r in rows}
        assert months == {4, 5}

    def test_breakdown_endpoint_404_unknown(self, client, db_session):
        resp = client.get(
            "/api/v1/planning/scenarios/no-such-sid/revisions/no-such-rid/breakdown"
        )
        assert resp.status_code == 404
