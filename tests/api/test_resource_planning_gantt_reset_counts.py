"""GET /resource-planning/resource-plans/{plan_id}/gantt response includes
reset_counts {pinned_dates, pinned_employees, edited_predecessors} so frontend
bulk-reset dropdown can disable buttons whose count = 0 and show numbers
like «Сбросить закреплённые даты (12)».
"""

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
    Employee,
    PhasePredecessor,
    PlanningScenario,
    ResourcePlan,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


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


def _emp(db_session, team: str, role: str) -> Employee:
    e = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name=f"{role.capitalize()}-rc",
        team=team,
        is_active=True,
        role=role,
    )
    db_session.add(e)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
    return e


@pytest.fixture
def seed_plan_with_pins(db_session):
    """Plan with 2 backlog items × phases; one pinned_start, one pinned_employee,
    one predecessors_user_set + PhasePredecessor row."""

    def _build():
        team = "T_RC"
        analyst = _emp(db_session, team, "analyst")
        _emp(db_session, team, "developer")

        item1 = BacklogItem(
            title="rc-item-1",
            priority=1,
            estimate_analyst_hours=16.0,
            estimate_dev_hours=24.0,
            estimate_qa_hours=8.0,
            estimate_opo_hours=0.0,
            assignee_employee_id=analyst.id,
        )
        item2 = BacklogItem(
            title="rc-item-2",
            priority=2,
            estimate_analyst_hours=8.0,
            estimate_dev_hours=16.0,
            estimate_qa_hours=0.0,
            estimate_opo_hours=0.0,
            assignee_employee_id=analyst.id,
        )
        db_session.add_all([item1, item2])
        db_session.flush()

        scenario = PlanningScenario(
            name="rc-scenario",
            quarter="Q2",
            year=2026,
            status="draft",
            team=team,
        )
        db_session.add(scenario)
        db_session.flush()
        for it in (item1, item2):
            db_session.add(
                ScenarioAllocation(
                    scenario_id=scenario.id,
                    backlog_item_id=it.id,
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

        a_pin_start = (
            db_session.query(ResourcePlanAssignment)
            .filter_by(plan_id=plan.id, backlog_item_id=item1.id, phase="analyst")
            .first()
        )
        a_pin_emp = (
            db_session.query(ResourcePlanAssignment)
            .filter_by(plan_id=plan.id, backlog_item_id=item1.id, phase="dev")
            .first()
        )
        a_pred_user = (
            db_session.query(ResourcePlanAssignment)
            .filter_by(plan_id=plan.id, backlog_item_id=item2.id, phase="analyst")
            .first()
        )
        pred_source = (
            db_session.query(ResourcePlanAssignment)
            .filter_by(plan_id=plan.id, backlog_item_id=item1.id, phase="qa")
            .first()
        )
        assert all([a_pin_start, a_pin_emp, a_pred_user, pred_source])

        a_pin_start.pinned_start = True
        a_pin_start.manual_edit_at = datetime.utcnow()

        a_pin_emp.pinned_employee = True
        a_pin_emp.manual_edit_at = datetime.utcnow()

        a_pred_user.predecessors_user_set = True
        a_pred_user.manual_edit_at = datetime.utcnow()

        db_session.add(
            PhasePredecessor(
                successor_assignment_id=a_pred_user.id,
                predecessor_assignment_id=pred_source.id,
            )
        )
        db_session.commit()
        return plan.id

    return _build


@pytest.fixture
def seed_clean_plan(db_session):
    """Plan with assignments but no pinned flags set."""

    def _build():
        team = "T_RC_CLEAN"
        analyst = _emp(db_session, team, "analyst")
        _emp(db_session, team, "developer")

        item = BacklogItem(
            title="rc-clean-1",
            priority=1,
            estimate_analyst_hours=8.0,
            estimate_dev_hours=8.0,
            estimate_qa_hours=0.0,
            estimate_opo_hours=0.0,
            assignee_employee_id=analyst.id,
        )
        db_session.add(item)
        db_session.flush()

        scenario = PlanningScenario(
            name="rc-clean-scenario",
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

    return _build


def test_gantt_returns_reset_counts(client, db_session, seed_plan_with_pins):
    plan_id = seed_plan_with_pins()
    resp = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert resp.status_code == 200, resp.text
    counts = resp.json()["reset_counts"]
    assert counts["pinned_dates"] >= 1
    assert counts["pinned_employees"] >= 1
    assert counts["edited_predecessors"] >= 1


def test_gantt_empty_pins_returns_zero_counts(client, db_session, seed_clean_plan):
    plan_id = seed_clean_plan()
    resp = client.get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    assert resp.status_code == 200, resp.text
    counts = resp.json()["reset_counts"]
    assert counts == {
        "pinned_dates": 0,
        "pinned_employees": 0,
        "edited_predecessors": 0,
    }
