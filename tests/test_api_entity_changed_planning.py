"""Проверяем, что мутирующие endpoints планирования публикуют entity_changed."""
import pytest
from unittest.mock import AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services.event_bus import get_event_bus


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_client(db, mock_bus):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: mock_bus
    return TestClient(app)


def _teardown():
    app.dependency_overrides.clear()


# ── seed helpers ──────────────────────────────────────────────────────────────

def _seed_backlog_item(db):
    from app.models import BacklogItem, Category, Issue, Project
    cat = Category(id="cat-rfa", code="initiatives_rfa", label="RFA", color="#000",
                   sort_order=1, is_system=True)
    proj = Project(id="proj-1", jira_project_id="p1", key="P", name="P", is_active=True)
    issue = Issue(id="iss-1", jira_issue_id="i1", key="P-1", summary="S",
                  issue_type="Epic", status="Open", project_id="proj-1",
                  category="initiatives_rfa")
    item = BacklogItem(id="bi-1", title="Item 1", issue_id="iss-1",
                       estimate_hours=10)
    db.add_all([cat, proj, issue, item])
    db.commit()
    return item


def _seed_scenario_with_allocation(db, item_id):
    from app.models import PlanningScenario, ScenarioAllocation
    sc = PlanningScenario(id="sc-1", name="Q1", year=2026, quarter="Q1", status="draft")
    db.add(sc)
    db.flush()
    alloc = ScenarioAllocation(id="al-1", scenario_id="sc-1",
                                backlog_item_id=item_id, included_flag=False,
                                planned_hours=0, sort_order=1.0)
    db.add(alloc)
    db.commit()
    return sc, alloc


# ── tests ─────────────────────────────────────────────────────────────────────

def test_create_scenario_publishes_planning(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post("/api/v1/planning/scenarios",
                        json={"name": "Q1", "year": 2026, "quarter": 1})
        assert r.status_code == 201, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning"]}
    )


def test_patch_allocation_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.patch(
            f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}",
            json={"included": True},
        )
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )


def test_patch_allocation_assignee_publishes_planning(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.patch(
            f"/api/v1/planning/scenarios/{sc.id}/allocations/{alloc.id}/assignee",
            json={"assignee_employee_id": None},
        )
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning"]}
    )


def test_approve_scenario_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/planning/scenarios/{sc.id}/approve", json={})
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )


def test_revert_scenario_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    # Approve first so we can revert
    db_session.get(sc.__class__, sc.id).status = "approved"
    db_session.commit()
    client = _make_client(db_session, mock_bus)
    try:
        r = client.post(f"/api/v1/planning/scenarios/{sc.id}/revert-to-draft")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )


def test_delete_scenario_publishes_planning_and_backlog(db_session):
    mock_bus = AsyncMock()
    item = _seed_backlog_item(db_session)
    sc, alloc = _seed_scenario_with_allocation(db_session, item.id)
    client = _make_client(db_session, mock_bus)
    try:
        r = client.delete(f"/api/v1/planning/scenarios/{sc.id}")
        assert r.status_code == 200, r.text
    finally:
        _teardown()
    mock_bus.publish.assert_called_once_with(
        {"type": "entity_changed", "entities": ["planning", "backlog"]}
    )
