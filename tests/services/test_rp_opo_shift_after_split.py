"""После cascade-split аналитика и сдвига второй части вправо,
ОПЭ должна переместиться за конец последней QA-части.

Воспроизводит ITL-398: пользователь разбил аналитика на 2 части
(cascade=True), сдвинул вторую часть вправо. ОПЭ оставалась на старой
дате (раньше окончания тестирования ч.2) → PREDECESSOR_VIOLATED.
"""

import uuid
from datetime import date

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


def _emp(db_session, team: str, role: str) -> Employee:
    e = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name=f"{role}-{team}",
        team=team,
        is_active=True,
        role=role,
    )
    db_session.add(e)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
    return e


def test_opo_shifts_after_cascade_split_and_move(db_session):
    team = "T_OPO_SHIFT"
    analyst = _emp(db_session, team, "analyst")
    _emp(db_session, team, "developer")

    item = BacklogItem(
        title="opo-shift-test",
        priority=1,
        estimate_analyst_hours=20.0,
        estimate_dev_hours=20.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=5.0,
        opo_analyst_ratio=1.0,  # вся ОПЭ на аналитика
        assignee_employee_id=analyst.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="opo-shift-scenario",
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

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    # split analyst на 2 части с каскадом
    from sqlalchemy import select

    analyst_row = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "analyst",
                ResourcePlanAssignment.part_number == 1,
            )
        )
        .scalars()
        .one()
    )
    svc.split_assignment(analyst_row.id, [10.0, 10.0], cascade=True)
    db_session.commit()

    # двигаем analyst part 2 вправо (далеко в июнь)
    analyst_2 = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "analyst",
                ResourcePlanAssignment.part_number == 2,
            )
        )
        .scalars()
        .one()
    )
    new_start = date(2026, 6, 15)
    analyst_2.start_date = new_start
    analyst_2.pinned_start = True
    db_session.commit()

    # пересчёт
    svc.compute_schedule(plan.id)
    db_session.expire_all()

    # OPO rows
    opo_rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "opo",
            )
        )
        .scalars()
        .all()
    )
    assert opo_rows, "OPO assignments must exist"

    # qa part 2 — последний предшественник OPO по ensure_default
    qa_2 = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "qa",
            )
            .order_by(ResourcePlanAssignment.part_number.desc())
        )
        .scalars()
        .first()
    )
    assert qa_2 is not None and qa_2.end_date is not None
    qa_2_end = qa_2.end_date

    for opo in opo_rows:
        assert opo.start_date is not None
        assert opo.start_date > qa_2_end, (
            f"OPO start {opo.start_date} должен быть > последней QA-части "
            f"({qa_2_end}); фаза стартует до окончания предшественника"
        )
