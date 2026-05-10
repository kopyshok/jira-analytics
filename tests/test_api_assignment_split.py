"""Tests for split / merge / clear-manual-edit endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def ready_plan(db_session):
    """План с одной инициативой и compute_schedule."""
    from app.models import (
        BacklogItem,
        Employee,
        PlanningScenario,
        ResourcePlan,
        ScenarioAllocation,
    )
    from app.models.employee_team import EmployeeTeam
    from app.services.resource_planning_service import ResourcePlanningService

    team = "T_SPLIT"

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=role.capitalize(),
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
        return e

    analyst = _emp("analyst")
    _emp("developer")

    item = BacklogItem(
        title="split-test",
        priority=1,
        estimate_analyst_hours=20.0,
        estimate_dev_hours=20.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=8.0,
        opo_analyst_ratio=0.5,
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="split-scenario",
        quarter="Q2",
        year=2026,
        status="draft",
        team=team,
    )
    db_session.add(scenario)
    db_session.flush()

    db_session.add(
        ScenarioAllocation(
            scenario_id=scenario.id,
            backlog_item_id=item.id,
            included_flag=True,
        )
    )

    plan = ResourcePlan(
        team=team,
        quarter="Q2",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)
    return plan.id


def _phase(db_session, plan_id, phase, part=1):
    from app.models import ResourcePlanAssignment

    return (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.phase == phase,
                ResourcePlanAssignment.part_number == part,
            )
        )
        .scalars()
        .first()
    )


def test_split_assignment_two_parts_with_cascade(client, db_session, ready_plan):
    a = _phase(db_session, ready_plan, "analyst")
    assert a is not None
    r = client.post(
        f"/api/v1/resource-planning/resource-plans/{ready_plan}/assignments/{a.id}/split",
        json={"parts": [12, 8], "cascade": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    parts = body["parts"]
    assert len(parts) == 2
    assert parts[0]["hours_allocated"] == 12
    assert parts[1]["hours_allocated"] == 8
    assert all(p["pinned_split"] is True for p in parts)
    cascaded = body["cascaded"]
    assert len(cascaded) >= 2  # хотя бы dev сплит


def test_merge_assignment_combines_parts(client, db_session, ready_plan):
    a = _phase(db_session, ready_plan, "analyst")
    assert a is not None
    # сначала сплит
    r = client.post(
        f"/api/v1/resource-planning/resource-plans/{ready_plan}/assignments/{a.id}/split",
        json={"parts": [12, 8], "cascade": False},
    )
    assert r.status_code == 200, r.text
    parts = r.json()["parts"]
    part1_id = parts[0]["id"]

    r2 = client.post(
        f"/api/v1/resource-planning/resource-plans/{ready_plan}/assignments/{part1_id}/merge",
    )
    assert r2.status_code == 200, r2.text
    merged = r2.json()["assignment"]
    assert merged["part_number"] == 1
    assert merged["hours_allocated"] == 20.0
    assert merged["pinned_split"] is False


def test_split_sum_mismatch_rejected(client, db_session, ready_plan):
    a = _phase(db_session, ready_plan, "analyst")
    assert a is not None
    r = client.post(
        f"/api/v1/resource-planning/resource-plans/{ready_plan}/assignments/{a.id}/split",
        json={"parts": [10, 5], "cascade": False},
    )
    assert r.status_code == 400


def test_clear_manual_edit_resets_pin_flags(client, db_session, ready_plan):
    a = _phase(db_session, ready_plan, "dev")
    assert a is not None
    # сначала закрепить через PATCH
    r = client.patch(
        f"/api/v1/resource-planning/resource-plans/{ready_plan}/assignments/{a.id}",
        json={"start_date": "2026-05-15"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_pinned"] is True

    # снять ручные правки
    r2 = client.delete(
        f"/api/v1/resource-planning/resource-plans/{ready_plan}/assignments/{a.id}/manual-edit",
    )
    assert r2.status_code == 200, r2.text
    body = r2.json()["assignment"]
    assert body["pinned_start"] is False
    assert body["pinned_employee"] is False
    assert body["pinned_split"] is False
    assert body["manual_edit_at"] is None
