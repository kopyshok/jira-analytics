"""PATCH start_date должен расширять end_date так, чтобы вместить hours_allocated.

Старое поведение сохраняло длительность фазы (new_end = end + delta_days),
что молча обрезало плановые часы при day_cap × duration < hours.

Теперь end_date и daily_hours_json пересчитываются через
_extend_window_for_hours, чтобы окно фазы вмещало все заявленные часы
(или дотягивалось до конца квартала).
"""

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
def dev_plan(db_session):
    """План Q2 2026 c одной dev-фазой на 40h, involvement=100%.

    Сценарий: pure dev (estimate_analyst_hours=0, qa=0, opo=0), чтобы
    получить ровно одно dev-назначение после compute_schedule, и можно
    было независимо проверить расширение окна.
    """
    from app.models import (
        BacklogItem,
        Employee,
        PlanningScenario,
        ResourcePlan,
        ResourcePlanAssignment,
        ScenarioAllocation,
    )
    from app.models.employee_team import EmployeeTeam
    from app.services.resource_planning_service import ResourcePlanningService

    team = "T_EXTEND"

    dev = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="Dev",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev.id, team=team, is_primary=True))

    item = BacklogItem(
        title="extend-test",
        priority=1,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=40.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        involvement_dev=1.0,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="extend-scenario",
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

    dev_assignment = (
        db_session.execute(
            select(ResourcePlanAssignment)
            .where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "dev",
            )
            .limit(1)
        )
        .scalars()
        .first()
    )
    assert dev_assignment is not None, "compute_schedule must create dev assignment"
    assert dev_assignment.hours_allocated and dev_assignment.hours_allocated > 0

    return {
        "plan_id": plan.id,
        "assignment_id": dev_assignment.id,
        "employee_id": dev.id,
    }


def test_patch_start_date_extends_end_to_fit_hours(client, db_session, dev_plan):
    """40h × 100% при cap=6h/день требует 7 рабочих дней.

    Mon 20.04.2026 + 6 weekday-skip (Sat 25 + Sun 26 пропущены) → Tue 28.04.
    daily_hours sum = 40.
    """
    from app.models import ResourcePlanAssignment

    resp = client.patch(
        f"/api/v1/resource-planning/resource-plans/{dev_plan['plan_id']}/assignments/{dev_plan['assignment_id']}",
        json={"start_date": "2026-04-20"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["start_date"] == "2026-04-20"
    assert body["end_date"] == "2026-04-28"

    daily = body.get("daily_hours") or {}
    assert daily, "daily_hours must be present after auto-extend"
    assert abs(sum(daily.values()) - 40.0) < 0.01
    # Все ключи должны принадлежать новому окну [20.04, 28.04],
    # никаких остатков от исходного расписания (1..9 апреля).
    assert set(daily.keys()) == {
        "2026-04-20",
        "2026-04-21",
        "2026-04-22",
        "2026-04-23",
        "2026-04-24",
        "2026-04-27",
        "2026-04-28",
    }

    a = db_session.get(ResourcePlanAssignment, dev_plan["assignment_id"])
    db_session.refresh(a)
    assert a.daily_hours_json
    assert a.out_of_quarter is False


def test_patch_with_explicit_end_date_does_not_auto_extend(
    client, db_session, dev_plan
):
    """Если пользователь явно передал end_date — auto-extend не запускается."""
    from app.models import ResourcePlanAssignment

    # Снимок daily_hours_json ДО PATCH — если auto-extend-ветка ошибочно
    # запустится при явном end_date, она перезапишет это значение через
    # _extend_window_for_hours.
    a_before = db_session.get(ResourcePlanAssignment, dev_plan["assignment_id"])
    daily_before = a_before.daily_hours_json
    db_session.expire_all()

    resp = client.patch(
        f"/api/v1/resource-planning/resource-plans/{dev_plan['plan_id']}/assignments/{dev_plan['assignment_id']}",
        json={"start_date": "2026-04-20", "end_date": "2026-04-22"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["start_date"] == "2026-04-20"
    # Явный end_date пользователя сохраняется как есть, auto-extend не вмешивается.
    assert body["end_date"] == "2026-04-22"

    db_session.expire_all()
    a_after = db_session.get(ResourcePlanAssignment, dev_plan["assignment_id"])
    assert a_after.end_date.isoformat() == "2026-04-22"
    # daily_hours_json не должен быть переписан хелпером расширения —
    # сравниваем со снимком до PATCH.
    assert a_after.daily_hours_json == daily_before
