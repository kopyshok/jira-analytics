"""Tests for scenario revision history: approve creates revision + items + snapshots."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    PlanningScenario,
    ScenarioAllocation,
    ScenarioCapacitySnapshot,
    ScenarioRevision,
    ScenarioRevisionItem,
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


def _make_scenario(db, team="TeamA", year=2026, quarter="Q2", status="draft"):
    s = PlanningScenario(
        id=_uid(), name="Test", year=year, quarter=quarter,
        status=status, team=team,
    )
    db.add(s)
    db.flush()
    return s


def _make_item(db, title="Init X"):
    item = BacklogItem(id=_uid(), title=title)
    db.add(item)
    db.flush()
    return item


def _make_employee(db, name="Alice", team="TeamA"):
    emp = Employee(
        id=_uid(),
        display_name=name,
        jira_account_id=_uid(),
        is_active=True,
        email=f"{name.lower().replace(' ', '_')}@test.com",
    )
    db.add(emp)
    db.flush()
    db.add(EmployeeTeam(
        id=_uid(), employee_id=emp.id, team=team, is_primary=True,
    ))
    db.flush()
    return emp


def _make_allocation(db, scenario_id, item_id, included=True):
    alloc = ScenarioAllocation(
        id=_uid(),
        scenario_id=scenario_id,
        backlog_item_id=item_id,
        included_flag=included,
        planned_hours=10.0 if included else 0.0,
    )
    db.add(alloc)
    db.flush()
    return alloc


class TestApproveCreatesRevision:
    def test_first_approve_creates_revision_number_1(self, client, db_session):
        scenario = _make_scenario(db_session)
        item = _make_item(db_session)
        _make_allocation(db_session, scenario.id, item.id, included=True)
        db_session.commit()

        resp = client.post(
            f"/api/v1/planning/scenarios/{scenario.id}/approve",
            json={"note": "Initial plan"},
        )
        assert resp.status_code == 200

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        assert rev is not None
        assert rev.revision_number == 1
        assert rev.note == "Initial plan"

    def test_first_approve_all_included_items_marked_included(self, client, db_session):
        scenario = _make_scenario(db_session)
        item1 = _make_item(db_session, "Task A")
        item2 = _make_item(db_session, "Task B")
        _make_allocation(db_session, scenario.id, item1.id, included=True)
        _make_allocation(db_session, scenario.id, item2.id, included=False)
        db_session.commit()

        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        items = db_session.query(ScenarioRevisionItem).filter_by(revision_id=rev.id).all()
        assert len(items) == 1
        assert items[0].action == "included"
        assert items[0].backlog_item_name == "Task A"

    def test_second_approve_records_diff(self, client, db_session):
        scenario = _make_scenario(db_session)
        item1 = _make_item(db_session, "Task A")
        item2 = _make_item(db_session, "Task B")
        _make_allocation(db_session, scenario.id, item1.id, included=True)
        alloc2 = _make_allocation(db_session, scenario.id, item2.id, included=False)
        db_session.commit()

        # First approval: only item1 included
        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})

        # Revert to draft
        client.post(f"/api/v1/planning/scenarios/{scenario.id}/revert-to-draft")

        # Exclude item1, include item2
        db_session.expire_all()
        alloc1 = db_session.query(ScenarioAllocation).filter_by(
            scenario_id=scenario.id, backlog_item_id=item1.id
        ).first()
        alloc1.included_flag = False
        alloc1.planned_hours = 0
        alloc2 = db_session.query(ScenarioAllocation).filter_by(
            scenario_id=scenario.id, backlog_item_id=item2.id
        ).first()
        alloc2.included_flag = True
        alloc2.planned_hours = 10
        db_session.commit()

        # Second approval
        client.post(
            f"/api/v1/planning/scenarios/{scenario.id}/approve",
            json={"note": "Replaced A with B"},
        )

        revisions = (
            db_session.query(ScenarioRevision)
            .filter_by(scenario_id=scenario.id)
            .order_by(ScenarioRevision.revision_number)
            .all()
        )
        assert len(revisions) == 2
        rev2_items = (
            db_session.query(ScenarioRevisionItem)
            .filter_by(revision_id=revisions[1].id)
            .all()
        )
        actions = {i.backlog_item_name: i.action for i in rev2_items}
        assert actions.get("Task B") == "included"
        assert actions.get("Task A") == "excluded"
        assert revisions[1].note == "Replaced A with B"

    def test_approve_already_approved_returns_409(self, client, db_session):
        scenario = _make_scenario(db_session)
        db_session.commit()

        client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})
        resp = client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})
        assert resp.status_code == 409

    def test_approve_no_team_skips_capacity_snapshot(self, client, db_session):
        scenario = _make_scenario(db_session, team=None)
        db_session.commit()

        resp = client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})
        assert resp.status_code == 200

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        snapshots = db_session.query(ScenarioCapacitySnapshot).filter_by(
            revision_id=rev.id
        ).all()
        assert snapshots == []

    def test_approve_with_team_creates_capacity_snapshots(self, client, db_session):
        scenario = _make_scenario(db_session, team="TeamSnap", year=2026, quarter="Q2")
        _make_employee(db_session, name="Bob", team="TeamSnap")
        db_session.commit()

        resp = client.post(f"/api/v1/planning/scenarios/{scenario.id}/approve", json={})
        assert resp.status_code == 200

        rev = db_session.query(ScenarioRevision).filter_by(scenario_id=scenario.id).first()
        snapshots = (
            db_session.query(ScenarioCapacitySnapshot)
            .filter_by(revision_id=rev.id)
            .all()
        )
        # Q2 = months 4, 5, 6 → 3 snapshots for 1 employee
        assert len(snapshots) == 3
        months = {s.month for s in snapshots}
        assert months == {4, 5, 6}
        for s in snapshots:
            assert s.employee_name == "Bob"
            assert s.norm_hours >= 0
            assert s.available_hours >= 0


class TestRevisionsEndpoint:
    def test_get_revisions_empty(self, client, db_session):
        scenario = _make_scenario(db_session)
        db_session.commit()

        resp = client.get(f"/api/v1/planning/scenarios/{scenario.id}/revisions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_revisions_returns_history(self, client, db_session):
        scenario = _make_scenario(db_session)
        item = _make_item(db_session, "Feature X")
        _make_allocation(db_session, scenario.id, item.id, included=True)
        db_session.commit()

        client.post(
            f"/api/v1/planning/scenarios/{scenario.id}/approve",
            json={"note": "Q2 plan"},
        )

        resp = client.get(f"/api/v1/planning/scenarios/{scenario.id}/revisions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["revision_number"] == 1
        assert data[0]["note"] == "Q2 plan"
        assert len(data[0]["items"]) == 1
        assert data[0]["items"][0]["action"] == "included"
        assert data[0]["items"][0]["backlog_item_name"] == "Feature X"

    def test_get_revisions_404_unknown_scenario(self, client, db_session):
        resp = client.get("/api/v1/planning/scenarios/no-such-id/revisions")
        assert resp.status_code == 404
