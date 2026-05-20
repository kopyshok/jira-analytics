"""POST /resource-planning/resource-plans/{plan_id}/bulk-clear endpoint.

Single endpoint clears pinned flags / user-set predecessors across ALL
assignments of a plan in one call. Modes: dates | employees |
predecessors | all. Auto-triggers compute_schedule on success.
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


@pytest.fixture
def seed_plan_with_pins(db_session):
    """Создаёт план с 2 инициативами × 4 фазами и проставляет:
    - pinned_start на одной фазе,
    - pinned_employee на другой,
    - predecessors_user_set + явное ребро PhasePredecessor на третьей.

    Возвращает callable, которое строит план и возвращает plan_id.
    """

    def _build():
        team = "T_BULK"

        def _emp(role: str) -> Employee:
            e = Employee(
                jira_account_id=uuid.uuid4().hex[:16],
                display_name=f"{role.capitalize()}-bulk",
                team=team,
                is_active=True,
                role=role,
            )
            db_session.add(e)
            db_session.flush()
            db_session.add(
                EmployeeTeam(employee_id=e.id, team=team, is_primary=True)
            )
            return e

        analyst = _emp("analyst")
        _emp("developer")

        item1 = BacklogItem(
            title="bulk-item-1",
            priority=1,
            estimate_analyst_hours=16.0,
            estimate_dev_hours=24.0,
            estimate_qa_hours=8.0,
            estimate_opo_hours=0.0,
            assignee_employee_id=analyst.id,
        )
        item2 = BacklogItem(
            title="bulk-item-2",
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
            name="bulk-scenario",
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

        # Первичный расчёт создаёт назначения.
        ResourcePlanningService(db_session).compute_schedule(plan.id)

        # Выбираем конкретные фазы детерминированно, чтобы синтетическое
        # ребро PhasePredecessor шло в одном направлении с дефолтной
        # цепочкой analyst→dev→qa и не создавало цикл при recompute.
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
        # successor — analyst фазы item2; predecessor — qa фазы item1.
        # Кросс-item edge: дефолтная цепочка такого ребра НЕ создаёт,
        # а значит UniqueConstraint не нарушится; цикл невозможен,
        # т.к. фазы принадлежат разным backlog_item.
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
        assert all([a_pin_start, a_pin_emp, a_pred_user, pred_source]), (
            "fixture expects 4 specific phase rows"
        )

        a_pin_start.pinned_start = True
        a_pin_start.manual_edit_at = datetime.utcnow()

        a_pin_emp.pinned_employee = True
        a_pin_emp.manual_edit_at = datetime.utcnow()

        a_pred_user.predecessors_user_set = True
        a_pred_user.manual_edit_at = datetime.utcnow()

        # Edge: item2.analyst → item2.dev. Совпадает с дефолтной цепочкой
        # (compute_schedule всё равно её создаст), но _snapshot_predecessors
        # запомнит её как user-set и при `predecessors` mode мы должны её
        # удалить вместе со флагом.
        db_session.add(
            PhasePredecessor(
                successor_assignment_id=a_pred_user.id,
                predecessor_assignment_id=pred_source.id,
            )
        )
        db_session.commit()
        return plan.id

    return _build


@pytest.mark.parametrize(
    "mode,check",
    [
        ("dates", lambda asss: all(not a.pinned_start for a in asss)),
        ("employees", lambda asss: all(not a.pinned_employee for a in asss)),
        (
            "predecessors",
            lambda asss: all(not a.predecessors_user_set for a in asss),
        ),
        (
            "all",
            lambda asss: all(
                not a.pinned_start
                and not a.pinned_employee
                and not a.pinned_split
                and not a.predecessors_user_set
                for a in asss
            ),
        ),
    ],
)
def test_bulk_clear_mode(client, db_session, seed_plan_with_pins, mode, check):
    plan_id = seed_plan_with_pins()
    resp = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/bulk-clear",
        json={"mode": mode},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cleared_count"] >= 1
    assert body["mode"] == mode
    db_session.expire_all()
    asss = (
        db_session.query(ResourcePlanAssignment)
        .filter_by(plan_id=plan_id)
        .all()
    )
    assert check(asss)


def test_bulk_clear_predecessors_drops_phase_predecessor_rows(
    client, db_session, seed_plan_with_pins
):
    plan_id = seed_plan_with_pins()
    successor_ids_user_set = [
        a.id
        for a in db_session.query(ResourcePlanAssignment)
        .filter_by(plan_id=plan_id, predecessors_user_set=True)
        .all()
    ]
    before = (
        db_session.query(PhasePredecessor)
        .filter(
            PhasePredecessor.successor_assignment_id.in_(successor_ids_user_set)
        )
        .count()
    )
    assert before > 0
    resp = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/bulk-clear",
        json={"mode": "predecessors"},
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    after = (
        db_session.query(PhasePredecessor)
        .filter(
            PhasePredecessor.successor_assignment_id.in_(successor_ids_user_set)
        )
        .count()
    )
    assert after == 0


def test_bulk_clear_unknown_mode_returns_422(client, seed_plan_with_pins):
    plan_id = seed_plan_with_pins()
    resp = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/bulk-clear",
        json={"mode": "frobnicate"},
    )
    assert resp.status_code == 422


def test_bulk_clear_unknown_plan_returns_404(client):
    resp = client.post(
        "/api/v1/resource-planning/resource-plans/nonexistent/bulk-clear",
        json={"mode": "dates"},
    )
    assert resp.status_code == 404


def test_bulk_clear_all_triggers_recompute(client, db_session, seed_plan_with_pins):
    plan_id = seed_plan_with_pins()
    plan = db_session.get(ResourcePlan, plan_id)
    plan.status = "ready"
    db_session.commit()
    resp = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/bulk-clear",
        json={"mode": "all"},
    )
    assert resp.status_code == 200, resp.text
    db_session.expire_all()
    plan = db_session.get(ResourcePlan, plan_id)
    assert plan.status == "ready"
