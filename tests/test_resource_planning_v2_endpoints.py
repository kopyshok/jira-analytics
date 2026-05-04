"""Tests for /api/v1/resource-planning-v2 endpoints."""

from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def test_client(test_db_session):
    def _get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_get_quality_returns_zeros_for_empty_plan(test_client: TestClient, test_db_session):
    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="ready")
    test_db_session.add(plan)
    test_db_session.commit()

    r = test_client.get(f"/api/v1/resource-planning-v2/{plan.id}/quality")
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"] == plan.id
    assert body["overload_days_pct"] == 0.0
    assert body["late_count"] == 0
    assert body["mean_utilization_pct"] == 0.0
    assert "computed_at" in body


def test_get_quality_404_for_unknown_plan(test_client: TestClient):
    r = test_client.get("/api/v1/resource-planning-v2/nonexistent/quality")
    assert r.status_code == 404


def test_optimize_creates_fork_and_returns_quality_diff(
    test_client: TestClient, test_db_session
):
    """POST /optimize: солвер возвращает OPTIMAL/FEASIBLE, форк создаётся с правильными полями."""
    # Seed: 1 dev employee + 1 BacklogItem + 1 plan + 1 assignment
    emp = Employee(
        jira_account_id="dev-001",
        display_name="Dev User",
        role="developer",
        team="TeamA",
        is_active=True,
    )
    test_db_session.add(emp)
    test_db_session.flush()

    item = BacklogItem(title="Test Initiative")
    test_db_session.add(item)
    test_db_session.flush()

    plan = ResourcePlan(team="TeamA", quarter="Q2", year=2026, status="ready")
    test_db_session.add(plan)
    test_db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=emp.id,
        hours_allocated=16.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
        is_pinned=False,
    )
    test_db_session.add(assignment)
    test_db_session.commit()

    # Мокаем PyJobShopSolverService.solve чтобы не зависеть от pyjobshop в тестах
    from app.services.pyjobshop_solver_service import SolverResult, SolverAssignment, PhaseAllocation

    fake_result: SolverResult = SolverResult(
        assignments=[
            SolverAssignment(
                backlog_item_id=item.id,
                assignee_employee_id=emp.id,
                start_date=date(2026, 4, 1),
                end_date=date(2026, 4, 10),
                phase_breakdown=[
                    PhaseAllocation(
                        phase="dev",
                        hours=16.0,
                        employee_id=emp.id,
                        start_date=date(2026, 4, 1),
                        end_date=date(2026, 4, 10),
                    )
                ],
            )
        ],
        infeasible_items=[],
        solver_status="OPTIMAL",
        solve_time_ms=42,
    )

    with patch(
        "app.api.endpoints.resource_planning_v2.PyJobShopSolverService.solve",
        return_value=fake_result,
    ):
        r = test_client.post(f"/api/v1/resource-planning-v2/{plan.id}/optimize")

    assert r.status_code == 200, r.text
    body = r.json()

    assert body["new_plan_id"] != plan.id
    assert body["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert "before" in body
    assert "after" in body

    # Проверяем форк в БД
    fork = test_db_session.get(ResourcePlan, body["new_plan_id"])
    assert fork is not None
    assert fork.label == "auto-PyJobShop"
    assert fork.parent_plan_id == plan.id
