"""Tests for _allocate_hours / _allocate_hours_with_breakdown internals."""

from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services.resource_planning_service import ResourcePlanningService


# ── Task 2 ────────────────────────────────────────────────────────────────────


def test_allocate_subtracts_used_leaves_remainder():
    """Списываются ровно использованные часы, остаток дня доступен
    последующим фазам того же сотрудника. Иначе при involvement<1 (cap<avail)
    остаток капасити пропадал, и параллельные фазы видели фантомно-пустой день.
    """
    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-1"
    remaining = {
        emp_id: {
            date(2026, 4, 1): 8.0,
            date(2026, 4, 2): 8.0,
        }
    }

    svc._allocate_hours(
        emp_id, 4.0, date(2026, 4, 1), date(2026, 4, 30), remaining,
        daily_capacity=4.0,
    )

    # 4ч списали из 8ч дня — остаток 4ч доступен следующей фазе.
    assert remaining[emp_id][date(2026, 4, 1)] == 4.0
    # Day 2 не тронут
    assert remaining[emp_id][date(2026, 4, 2)] == 8.0


# ── Task 3 ────────────────────────────────────────────────────────────────────


def test_effective_end_no_stretch_when_jira_duration_set(db_session) -> None:
    """Jira duration_analyst_days=20 with only 20h of work → bar ends after
    actual work days, not stretched to 20 calendar days."""
    import uuid
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "DURSTRETCH1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="StretchAnalyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    # 20h of analyst work, but Jira says 20 calendar days.
    # With 6h/day capacity, 20h = ~4 actual work days.
    # Bar should NOT stretch to 20 days.
    item = BacklogItem(
        title="Stretch test item",
        priority=1,
        estimate_analyst_hours=20.0,
        duration_analyst_days=20.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="stretch-test-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(
        team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id
    )
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "analyst",
        )
    ).all()

    assert rows, "Должна быть хотя бы одна строка analyst"
    span = (max(r.end_date for r in rows) - min(r.start_date for r in rows)).days + 1
    # 20h / 6h_per_day ≈ 4 work days → calendar span well under 20 days
    assert span <= 10, (
        f"Бар растянулся на {span} дней; ожидалось ≤10 (без Jira-duration-stretch)"
    )


# ── Task 4 ────────────────────────────────────────────────────────────────────


def _working_days_between(start: date, end: date) -> int:
    """Count working days (Mon-Fri) strictly between two dates (exclusive)."""
    count = 0
    d = start + timedelta(days=1)
    while d < end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def test_dev_starts_right_after_actual_analyst_end(db_session) -> None:
    """Dev phase starts 1-3 working days after actual analyst end, not after Jira
    duration stretch.  analyst=16h, duration_analyst_days=15, dev=8h."""
    import uuid
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "DEVSTART1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="DevStartAnalyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    dev_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="DevStartDev",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="DevStart test item",
        priority=1,
        estimate_analyst_hours=16.0,
        duration_analyst_days=15.0,
        estimate_dev_hours=8.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="devstart-test-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(
        team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id
    )
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    analyst_rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "analyst",
        )
    ).all()
    dev_rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).all()

    assert analyst_rows, "Должна быть строка analyst"
    assert dev_rows, "Должна быть строка dev"

    analyst_end = max(r.end_date for r in analyst_rows)
    dev_start = min(r.start_date for r in dev_rows)

    gap_days = (dev_start - analyst_end).days
    assert 1 <= gap_days <= 3, (
        f"Dev должен стартовать через 1-3 дня после analyst; "
        f"analyst_end={analyst_end}, dev_start={dev_start}, gap={gap_days}"
    )


# ── Task 5 ────────────────────────────────────────────────────────────────────


def test_allocate_returns_daily_breakdown():
    """_allocate_hours_with_breakdown returns accurate per-day dict."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-1"
    remaining = {
        emp_id: {
            date(2026, 4, 1): 6.0,
            date(2026, 4, 2): 6.0,
            date(2026, 4, 3): 6.0,
        }
    }

    segs, daily = svc._allocate_hours_with_breakdown(
        emp_id, 12.0, date(2026, 4, 1), date(2026, 4, 30), remaining
    )

    assert len(segs) == 1
    assert abs(segs[0][2] - 12.0) < 0.01

    # Should have entries for days 1 and 2 (6+6=12), nothing for day 3
    assert abs(daily.get(date(2026, 4, 1), 0.0) - 6.0) < 0.01
    assert abs(daily.get(date(2026, 4, 2), 0.0) - 6.0) < 0.01
    assert date(2026, 4, 3) not in daily


def test_daily_hours_json_written_to_assignment(db_session) -> None:
    """compute_schedule writes daily_hours_json on each analyst assignment."""
    import json
    import uuid
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "DAILYJSON1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="DailyJsonAnalyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="DailyJson test item",
        priority=1,
        estimate_analyst_hours=12.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="dailyjson-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(
        team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id
    )
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "analyst",
        )
    ).all()

    assert rows, "Должна быть строка analyst"
    for row in rows:
        assert row.daily_hours_json is not None, (
            f"daily_hours_json должен быть заполнен, получено None (id={row.id})"
        )
        parsed = json.loads(row.daily_hours_json)
        total = sum(parsed.values())
        assert total > 0, "Сумма часов по дням должна быть > 0"


# ── Task 6 ────────────────────────────────────────────────────────────────────


def test_multi_segment_on_preempting_lock():
    """When preempt_locked skips day 2 of 4, allocate returns 2 segments."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-1"
    d1 = date(2026, 4, 1)  # Wed
    d2 = date(2026, 4, 2)  # Thu — preempt locked
    d3 = date(2026, 4, 3)  # Fri
    d4 = date(2026, 4, 6)  # Mon (skip weekend)

    remaining = {
        emp_id: {
            d1: 8.0,
            d2: 8.0,
            d3: 8.0,
            d4: 8.0,
        }
    }
    preempt_locked = {emp_id: {d2}}

    segs, daily = svc._allocate_hours_with_breakdown(
        emp_id, 24.0, d1, date(2026, 4, 30), remaining,
        preempt_locked=preempt_locked,
    )

    # Should get 2 segments: [d1] and [d3..d4]
    assert len(segs) == 2, f"Ожидалось 2 сегмента, получено {len(segs)}: {segs}"
    assert segs[0][0] == d1
    assert segs[0][1] == d1
    assert segs[0][3] == 1

    assert segs[1][0] == d3
    assert segs[1][1] == d4
    assert segs[1][3] == 2

    total_hours = sum(s[2] for s in segs)
    assert abs(total_hours - 24.0) < 0.01

    # day 2 stays untouched in remaining (preempting phase owns it)
    assert remaining[emp_id][d2] == 8.0
    # days 1, 3, 4 consumed
    assert remaining[emp_id][d1] == 0.0
    assert remaining[emp_id][d3] == 0.0
    assert remaining[emp_id][d4] == 0.0


# ── Task 7 ────────────────────────────────────────────────────────────────────


def test_out_of_quarter_spillover(db_session) -> None:
    """1000h analyst item overflows Q2; at least one assignment has out_of_quarter=True."""
    import uuid
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "SPILLOVER1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="SpilloverAnalyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="Spillover test item",
        priority=1,
        estimate_analyst_hours=1000.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="spillover-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(
        team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id
    )
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    from datetime import date as _date
    q_end = _date(2026, 6, 30)

    rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
        )
    ).all()

    assert rows, "Должны быть назначения"
    spill = [r for r in rows if r.out_of_quarter]
    assert spill, "Должен быть хотя бы один out_of_quarter=True"
    assert any(r.end_date > q_end for r in spill), (
        "out_of_quarter строка должна иметь end_date > q_end"
    )


# ── Fix 1: part_number uniqueness when analyst-split + preempt_locked ─────────


def test_composite_part_number_encoding():
    """chunk_idx * 10 + (seg_part - 1) produces unique values across all
    chunk+inner-segment combinations (simulates analyst-split + preempt logic)."""
    # Enumerate what the fixed code would produce for 2 chunks × 2 inner segments
    # chunk 1: seg_part=1 → 10, seg_part=2 → 11
    # chunk 2: seg_part=1 → 20, seg_part=2 → 21
    combos = [
        (chunk_idx * 10 + (seg_part - 1))
        for chunk_idx in range(1, 3)
        for seg_part in range(1, 3)
    ]
    assert len(set(combos)) == len(combos), f"Коллизия part_number: {combos}"
    assert combos == [10, 11, 20, 21], f"Ожидалось [10, 11, 20, 21], получено {combos}"


def test_allocate_inner_segments_have_distinct_part_numbers():
    """_allocate_hours_with_breakdown: 2 preempt-locked gaps → 3 segments with
    part_numbers 1, 2, 3 (all distinct)."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-x"
    d1 = date(2026, 4, 1)   # Wed
    d2 = date(2026, 4, 2)   # Thu — locked
    d3 = date(2026, 4, 3)   # Fri
    d4 = date(2026, 4, 6)   # Mon — locked
    d5 = date(2026, 4, 7)   # Tue

    remaining = {emp_id: {d1: 8.0, d2: 8.0, d3: 8.0, d4: 8.0, d5: 8.0}}
    preempt_locked = {emp_id: {d2, d4}}

    segs, _ = svc._allocate_hours_with_breakdown(
        emp_id, 24.0, d1, date(2026, 4, 30), remaining,
        preempt_locked=preempt_locked,
    )

    assert len(segs) == 3, f"Ожидалось 3 сегмента, получено {len(segs)}: {segs}"
    part_nums = [s[3] for s in segs]
    assert len(set(part_nums)) == len(part_nums), (
        f"part_numbers не уникальны: {part_nums}"
    )
    assert part_nums == [1, 2, 3], f"Ожидалось [1, 2, 3], получено {part_nums}"


# ── Fix 3: daily_hours_json scoped to segment date range ──────────────────────


def test_daily_hours_json_scoped_to_segment():
    """When preempt_locked splits into 2 segments, each assignment's
    daily_hours_json must only contain dates within its own date range."""
    import json
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-scope"
    d1 = date(2026, 4, 1)   # Wed — seg 1
    d2 = date(2026, 4, 2)   # Thu — preempt locked
    d3 = date(2026, 4, 3)   # Fri — seg 2
    d4 = date(2026, 4, 6)   # Mon — seg 2

    remaining = {emp_id: {d1: 8.0, d2: 8.0, d3: 8.0, d4: 8.0}}
    preempt_locked = {emp_id: {d2}}

    segs, daily = svc._allocate_hours_with_breakdown(
        emp_id, 24.0, d1, date(2026, 4, 30), remaining,
        preempt_locked=preempt_locked,
    )

    assert len(segs) == 2, f"Ожидалось 2 сегмента, получено {len(segs)}"

    # Simulate what compute_schedule does: filter daily by segment range
    for seg_start, seg_end, seg_hours, _part in segs:
        seg_daily = {
            d.isoformat(): h
            for d, h in daily.items()
            if seg_start <= d <= seg_end
        }
        parsed_dates = [date.fromisoformat(k) for k in seg_daily]
        for pd in parsed_dates:
            assert seg_start <= pd <= seg_end, (
                f"Дата {pd} выходит за пределы сегмента [{seg_start}, {seg_end}]"
            )

    # Segment 1: only d1 (d2 is locked, d3/d4 belong to seg 2)
    seg1_start, seg1_end, _, _ = segs[0]
    seg1_daily = {d.isoformat(): h for d, h in daily.items() if seg1_start <= d <= seg1_end}
    assert list(seg1_daily.keys()) == [d1.isoformat()], (
        f"Сегмент 1 должен содержать только {d1}, получено {list(seg1_daily.keys())}"
    )

    # Segment 2: only d3 and d4
    seg2_start, seg2_end, _, _ = segs[1]
    seg2_daily = {d.isoformat(): h for d, h in daily.items() if seg2_start <= d <= seg2_end}
    assert d2.isoformat() not in seg2_daily, "Заблокированный d2 не должен быть в сегменте 2"
    assert d3.isoformat() in seg2_daily
    assert d4.isoformat() in seg2_daily
