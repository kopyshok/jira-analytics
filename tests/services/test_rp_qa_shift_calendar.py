"""TDD: QA daily_hours_json recomputed via production calendar after predecessor shift.

Bug: _shift_to_obey_predecessors blind-shifts QA daily keys by delta days, which
can land them on Saturday/Sunday when the original layout ended on a Friday.
Fix: for phase == "qa", recompute daily layout from scratch using the production
calendar + involvement_qa coefficient.
"""

import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

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
from app.models.production_calendar_day import ProductionCalendarDay
from app.services.resource_planning_service import ResourcePlanningService


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def qa_shift_plan(db_session):
    """
    Seed:
      - Dev assignment ends on Friday (2026-06-05, a Friday)
      - QA assignment currently starts before that date (will need shifting)
      - PhasePredecessor: QA successor, dev predecessor
      - ProductionCalendarDay rows covering the test window (Mon-Fri = 6h, Sat/Sun = 0h via weekday check)
      - BacklogItem with estimate_qa_hours=16, no involvement_qa (None → 1.0 fallback)

    After _shift_to_obey_predecessors:
      - QA start_date must be Monday 2026-06-08 (next working day after Friday 2026-06-05)
      - All daily_hours_json keys must be weekdays
    """
    team = "T_QA_SHIFT"

    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="Dev-qa-shift",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="qa-shift-test",
        priority=1,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=24.0,
        estimate_qa_hours=16.0,
        estimate_opo_hours=0.0,
        opo_analyst_ratio=0.5,
        # involvement_qa intentionally None → fallback to 1.0
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="qa-shift-scenario",
        quarter="Q2",
        year=2026,
        status="draft",
        team=team,
    )
    db_session.add(scenario)
    db_session.flush()

    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id,
        backlog_item_id=item.id,
        included_flag=True,
    ))

    plan = ResourcePlan(
        team=team,
        quarter="Q2",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.flush()

    # Dev ends Friday 2026-06-05
    dev_end = date(2026, 6, 5)  # Friday
    assert dev_end.weekday() == 4, "setup: dev_end must be Friday"

    dev_assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=emp.id,
        part_number=1,
        hours_allocated=24.0,
        start_date=date(2026, 6, 2),  # Monday
        end_date=dev_end,
        daily_hours_json=json.dumps({
            "2026-06-02": 6.0,
            "2026-06-03": 6.0,
            "2026-06-04": 6.0,
            "2026-06-05": 6.0,
        }),
    )
    db_session.add(dev_assignment)
    db_session.flush()

    # QA starts 2026-06-01 (before dev ends) — needs to shift forward.
    # Build a QA daily layout that originally starts on Wednesday 2026-05-27
    # so that blind-shifting by delta=9 days would land some keys on Sat/Sun.
    # Original start: 2026-05-27 (Wed), end: 2026-05-29 (Fri) + next Mon/Tue.
    # delta = new_start (2026-06-08 Mon) - 2026-06-01 = 7 days → keys shift by 7
    # Original layout Mon 2026-06-02 → blind shift → Mon 2026-06-09 (still ok).
    # To expose the bug we craft original keys that straddle a weekend:
    # keys: Wed 2026-05-27, Thu 2026-05-28, Fri 2026-05-29, Mon 2026-06-01, Tue 2026-06-02
    # blind shift +7 → Wed 2026-06-03, Thu 2026-06-04, Fri 2026-06-05, Mon 2026-06-08, Tue 2026-06-09
    # But new_start = dev_end + 1 = 2026-06-06 (Saturday!) unless we clamp.
    # Cleaner: original QA start = 2026-06-01 (Mon), dev ends Fri 2026-06-05.
    # delta = 06-06 - 06-01 = 5 days. Keys shift by 5:
    # Mon 06-01 → Sat 06-06 ← WEEKEND BUG
    # Tue 06-02 → Sun 06-07 ← WEEKEND BUG
    # Wed 06-03 → Mon 06-08
    # Thu 06-04 → Tue 06-09
    qa_orig_daily = {
        "2026-06-01": 6.0,
        "2026-06-02": 6.0,
        "2026-06-03": 4.0,  # last partial day
    }
    qa_assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="qa",
        employee_id=None,
        part_number=1,
        hours_allocated=16.0,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        daily_hours_json=json.dumps(qa_orig_daily),
    )
    db_session.add(qa_assignment)
    db_session.flush()

    # Predecessor: QA ← dev
    db_session.add(PhasePredecessor(
        successor_assignment_id=qa_assignment.id,
        predecessor_assignment_id=dev_assignment.id,
    ))

    db_session.commit()
    return plan, dev_assignment, qa_assignment, item


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_qa_shift_lands_on_weekdays(db_session, qa_shift_plan):
    """After _shift_to_obey_predecessors, QA must start on a weekday and
    all daily_hours_json keys must be weekdays (Mon-Fri)."""
    plan, dev_asgn, qa_asgn, item = qa_shift_plan

    svc = ResourcePlanningService(db_session)

    # Build preds map: {successor_id: [predecessor_id]}
    preds = {qa_asgn.id: [dev_asgn.id]}
    assignments = [dev_asgn, qa_asgn]

    q_start = date(2026, 4, 1)
    q_end = date(2026, 6, 30)

    svc._shift_to_obey_predecessors(assignments, preds, q_start, q_end)

    # QA must start on the Monday after dev ends (dev ends Friday 2026-06-05)
    expected_start = date(2026, 6, 8)  # Monday
    assert qa_asgn.start_date == expected_start, (
        f"QA start_date should be {expected_start}, got {qa_asgn.start_date}"
    )

    # start_date and end_date must be weekdays
    assert qa_asgn.start_date.weekday() < 5, (
        f"QA start_date {qa_asgn.start_date} is a weekend"
    )
    assert qa_asgn.end_date.weekday() < 5, (
        f"QA end_date {qa_asgn.end_date} is a weekend"
    )

    # All daily_hours_json keys must be weekdays
    assert qa_asgn.daily_hours_json is not None
    daily = json.loads(qa_asgn.daily_hours_json)
    assert daily, "daily_hours_json must not be empty"
    for k, v in daily.items():
        d = date.fromisoformat(k)
        assert d.weekday() < 5, (
            f"daily_hours_json contains weekend key {k} (weekday={d.weekday()})"
        )
        assert v > 0, f"daily_hours_json key {k} has zero hours"


def test_qa_split_part_uses_own_hours_after_shift(db_session):
    """Split QA: каждая часть после shift расходует ТОЛЬКО свои часы,
    не суммарные QA-часы инициативы. Иначе для 5ч-части layout
    раздувается на 3-4 рабочих дня (как если бы у этой строки 20ч),
    бар наезжает на следующую фазу и стартует одновременно с
    предшественником вместо «день после конца».
    """
    team = "T_QA_SPLIT"
    emp = Employee(
        jira_account_id=_uid()[:16],
        display_name="Разраб-qa-split",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="qa-split",
        priority=1,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=24.0,
        estimate_qa_hours=20.0,  # total — split на 3 части
        estimate_opo_hours=0.0,
        opo_analyst_ratio=0.5,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(name="qa-split-s", quarter="Q2", year=2026, status="draft", team=team)
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.flush()

    # Dev part 3 (предшественник QA part 3) заканчивает во вторник 2026-06-23
    dev_p3 = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="dev",
        employee_id=emp.id, part_number=3, hours_allocated=8.0,
        start_date=date(2026, 6, 19), end_date=date(2026, 6, 23),
        daily_hours_json=json.dumps({"2026-06-19": 4.0, "2026-06-22": 4.0}),
        pinned_split=True,
    )
    # QA part 3 — 5ч (одна из трёх частей split), стоит ДО конца своего dev.
    qa_p3 = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="qa",
        employee_id=None, part_number=3, hours_allocated=5.0,
        start_date=date(2026, 6, 22), end_date=date(2026, 6, 24),
        daily_hours_json=json.dumps({"2026-06-22": 5.0}),
        pinned_split=True,
    )
    db_session.add_all([dev_p3, qa_p3])
    db_session.flush()
    db_session.add(PhasePredecessor(
        successor_assignment_id=qa_p3.id,
        predecessor_assignment_id=dev_p3.id,
    ))
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    preds = {qa_p3.id: [dev_p3.id]}
    svc._shift_to_obey_predecessors([dev_p3, qa_p3], preds, date(2026, 4, 1), date(2026, 6, 30))

    # QA part 3 должна стартовать НЕ РАНЬШЕ 24.06 (день после dev part 3 end)
    assert qa_p3.start_date >= date(2026, 6, 24), (
        f"QA part 3 стартует {qa_p3.start_date}, до конца dev part 3 (23.06)"
    )
    # Расход 5ч → ОДИН день при cap=6ч/день (DEFAULT_HOURS_PER_DAY), не 3-4.
    daily = json.loads(qa_p3.daily_hours_json)
    assert sum(daily.values()) == pytest.approx(5.0, abs=0.01)
    assert len(daily) == 1, (
        f"QA part 3 раздулась до {len(daily)} дней — должно быть 1 для 5ч"
    )


def test_qa_split_drift_rebuilds_when_delta_zero(db_session):
    """Если QA-part уже стоит ровно на «day after pred» (delta=0), но в
    daily_hours_json остался устаревший расход на item-total часы
    (например, 20ч вместо 7.5ч после изменения логики `_phase_hours`),
    shift должен ВСЁ РАВНО пересобрать раскладку под фактические
    a.hours_allocated. Иначе раскладка остаётся stale и фронт показывает
    20ч в карточке split-части.
    """
    team = "T_QA_DRIFT"
    emp = Employee(
        jira_account_id=_uid()[:16],
        display_name="Разраб-qa-drift",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="qa-drift",
        priority=1,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=20.0,
        estimate_qa_hours=20.0,
        estimate_opo_hours=0.0,
        opo_analyst_ratio=0.5,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(name="qa-drift-s", quarter="Q2", year=2026, status="draft", team=team)
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.flush()

    # Dev part 1 заканчивает Пн 06.04
    dev_p1 = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="dev",
        employee_id=emp.id, part_number=1, hours_allocated=10.0,
        start_date=date(2026, 4, 6), end_date=date(2026, 4, 6),
        daily_hours_json=json.dumps({"2026-04-06": 10.0}),
        pinned_split=True,
    )
    # QA part 1: hours_allocated=7.5, но daily_hours_json содержит 20ч
    # (артефакт прошлой логики shift, считавшей по item-total).
    qa_p1 = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="qa",
        employee_id=None, part_number=1, hours_allocated=7.5,
        start_date=date(2026, 4, 7), end_date=date(2026, 4, 9),
        daily_hours_json=json.dumps({"2026-04-07": 8.0, "2026-04-08": 8.0, "2026-04-09": 4.0}),
        pinned_split=True,
    )
    db_session.add_all([dev_p1, qa_p1])
    db_session.flush()
    db_session.add(PhasePredecessor(
        successor_assignment_id=qa_p1.id,
        predecessor_assignment_id=dev_p1.id,
    ))
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    preds = {qa_p1.id: [dev_p1.id]}
    # new_start = dev_p1.end+1 = 07.04, qa_p1.start_date=07.04 → delta=0.
    # Под старой логикой continue → daily остаётся 20ч.
    svc._shift_to_obey_predecessors([dev_p1, qa_p1], preds, date(2026, 4, 1), date(2026, 6, 30))

    daily = json.loads(qa_p1.daily_hours_json)
    assert sum(daily.values()) == pytest.approx(7.5, abs=0.01), (
        f"QA part 1 daily total = {sum(daily.values())}, ожидался 7.5"
    )
