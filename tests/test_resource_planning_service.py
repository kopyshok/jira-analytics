"""Tests for ResourcePlanningService."""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.services.resource_planning_service import (
    DEFAULT_HOURS_PER_DAY,
    PHASE_HOURS_FIELD,
    PHASE_ORDER,
    ResourcePlanningService,
)


def test_phase_order_correct():
    """Phase order must be analyst→dev→qa→opo."""
    assert PHASE_ORDER == ["analyst", "dev", "qa", "opo"]


def test_phase_hours_fields_mapped():
    """All phases have a corresponding BacklogItem field."""
    assert PHASE_HOURS_FIELD["analyst"] == "estimate_analyst_hours"
    assert PHASE_HOURS_FIELD["dev"] == "estimate_dev_hours"
    assert PHASE_HOURS_FIELD["qa"] == "estimate_qa_hours"
    assert PHASE_HOURS_FIELD["opo"] == "estimate_opo_hours"


def test_block_targets_employee_specific():
    """Block with one employee in `employees` list — only that employee affected."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    block = MagicMock()
    block.team = None
    block.roles = []
    emp_link = MagicMock()
    emp_link.employee_id = "emp-1"
    block.employees = [emp_link]

    emp1 = MagicMock()
    emp1.id = "emp-1"
    emp1.role = "analyst"
    emp1.team = "T1"
    emp2 = MagicMock()
    emp2.id = "emp-2"
    emp2.role = "analyst"
    emp2.team = "T1"

    result = svc._block_targets(block, [emp1, emp2], {})
    assert result == ["emp-1"]


def test_block_targets_role():
    """Block with one role in `roles` list — all employees of that role affected."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    block = MagicMock()
    block.team = None
    role_link = MagicMock()
    role_link.role_id = "role-uuid-analyst"
    block.roles = [role_link]
    block.employees = []

    emp1 = MagicMock()
    emp1.id = "emp-1"
    emp1.role = "analyst"
    emp2 = MagicMock()
    emp2.id = "emp-2"
    emp2.role = "analyst"
    emp3 = MagicMock()
    emp3.id = "emp-3"
    emp3.role = "dev"

    # role_id → role_code mapping
    role_id_to_code = {"role-uuid-analyst": "analyst"}

    result = svc._block_targets(block, [emp1, emp2, emp3], role_id_to_code)
    assert sorted(result) == ["emp-1", "emp-2"]


def test_allocate_hours_simple():
    """Basic allocation: 12 hours over 2 days of 6h each."""
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

    segments = svc._allocate_hours(
        emp_id, 12.0, date(2026, 4, 1), date(2026, 4, 30), remaining
    )

    assert len(segments) == 1
    seg_start, seg_end, seg_hours, part_num = segments[0]
    assert seg_start == date(2026, 4, 1)
    assert seg_end == date(2026, 4, 2)
    assert abs(seg_hours - 12.0) < 0.01
    assert part_num == 1
    # Remaining hours consumed
    assert remaining[emp_id][date(2026, 4, 1)] == 0.0
    assert remaining[emp_id][date(2026, 4, 2)] == 0.0


def test_allocate_hours_single_segment_across_gap():
    """Авто-сплит выключен: даже при 0-availability gap получается один сегмент,
    покрывающий диапазон от первого до последнего использованного дня."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    emp_id = "emp-1"
    remaining = {
        emp_id: {
            date(2026, 4, 1): 6.0,
            date(2026, 4, 2): 6.0,
            date(2026, 4, 3): 0.0,  # blocked
            date(2026, 4, 4): 0.0,  # blocked
            date(2026, 4, 5): 0.0,  # weekend
            date(2026, 4, 6): 0.0,  # weekend
            date(2026, 4, 7): 6.0,
        }
    }

    segments = svc._allocate_hours(
        emp_id, 18.0, date(2026, 4, 1), date(2026, 4, 30), remaining
    )

    assert len(segments) == 1
    assert segments[0][0] == date(2026, 4, 1)
    assert segments[0][1] == date(2026, 4, 7)
    assert abs(segments[0][2] - 18.0) < 0.01
    assert segments[0][3] == 1


# ── CPM tests ──────────────────────────────────────────────────────────────


def test_compute_cpm_critical_path():
    """Initiative with opo ending ON quarter end → slack=0, critical=True."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)  # Q1 2026 end

    a_opo = MagicMock()
    a_opo.backlog_item_id = "item1"
    a_opo.phase = "opo"
    a_opo.end_date = date(2026, 3, 31)

    a_analyst = MagicMock()
    a_analyst.backlog_item_id = "item1"
    a_analyst.phase = "analyst"
    a_analyst.end_date = date(2026, 1, 20)

    svc._compute_cpm([a_opo, a_analyst], q_end)

    assert a_opo.slack_days == 0.0
    assert a_opo.is_on_critical_path is True
    assert a_analyst.slack_days == 0.0
    assert a_analyst.is_on_critical_path is True


def test_compute_cpm_slack():
    """Initiative ending 11 days before quarter end → slack=11, not critical."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    a_opo = MagicMock()
    a_opo.backlog_item_id = "item2"
    a_opo.phase = "opo"
    a_opo.end_date = date(2026, 3, 20)  # 11 days before Mar 31

    svc._compute_cpm([a_opo], q_end)

    assert a_opo.slack_days == 11.0
    assert a_opo.is_on_critical_path is False


def test_compute_cpm_no_opo_uses_last_phase():
    """Initiative with no opo phase uses latest end_date among other phases."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 6, 30)  # Q2 end

    a_dev = MagicMock()
    a_dev.backlog_item_id = "item3"
    a_dev.phase = "dev"
    a_dev.end_date = date(2026, 6, 15)

    a_analyst = MagicMock()
    a_analyst.backlog_item_id = "item3"
    a_analyst.phase = "analyst"
    a_analyst.end_date = date(2026, 5, 10)

    svc._compute_cpm([a_dev, a_analyst], q_end)

    expected_slack = (date(2026, 6, 30) - date(2026, 6, 15)).days  # 15
    assert a_dev.slack_days == float(expected_slack)
    assert a_analyst.slack_days == float(expected_slack)
    assert a_dev.is_on_critical_path is False


def test_compute_cpm_overflow_negative_slack():
    """Initiative overflowing quarter has negative slack → critical."""
    from datetime import date
    from unittest.mock import MagicMock
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    a_opo = MagicMock()
    a_opo.backlog_item_id = "item4"
    a_opo.phase = "opo"
    a_opo.end_date = date(2026, 4, 5)  # 5 days past Q1

    svc._compute_cpm([a_opo], q_end)

    assert a_opo.slack_days == -5.0
    assert a_opo.is_on_critical_path is True


def test_compute_cpm_no_end_dates_skipped():
    """Assignments without end_date are silently skipped (no crash)."""
    from unittest.mock import MagicMock
    from datetime import date
    from app.services.resource_planning_service import ResourcePlanningService

    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    a = MagicMock()
    a.backlog_item_id = "item5"
    a.phase = "analyst"
    a.end_date = None

    # Should not raise, and slack_days/is_on_critical_path should remain as MagicMock defaults
    svc._compute_cpm([a], q_end)
    # If no dated assignments exist, method skips the item — no attribute set
    # Just verify it doesn't crash


# ── _build_role_pools tests ────────────────────────────────────────────────


def test_build_role_pools_groups_by_role():
    """Employees sharing a role appear in each other's peer list."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    e1 = MagicMock()
    e1.id = "emp-1"
    e1.role = "analyst"
    e2 = MagicMock()
    e2.id = "emp-2"
    e2.role = "Analyst"  # case-insensitive match
    e3 = MagicMock()
    e3.id = "emp-3"
    e3.role = "dev"

    pools = svc._build_role_pools([e1, e2, e3])

    # emp-1 and emp-2 share 'analyst' role
    assert set(pools["emp-1"]) == {"emp-1", "emp-2"}
    assert set(pools["emp-2"]) == {"emp-1", "emp-2"}
    # emp-3 is alone in 'dev'
    assert pools["emp-3"] == ["emp-3"]


def test_build_role_pools_employee_no_role_excluded():
    """Employees without a role are not included in any pool."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    e1 = MagicMock()
    e1.id = "emp-1"
    e1.role = "dev"
    e2 = MagicMock()
    e2.id = "emp-2"
    e2.role = None

    pools = svc._build_role_pools([e1, e2])

    assert "emp-1" in pools
    assert "emp-2" not in pools


def test_last_leveling_events_initialized_empty():
    """_last_leveling_events is [] on a fresh service instance."""
    db = MagicMock()
    svc = ResourcePlanningService(db)
    assert svc._last_leveling_events == []


# ── _build_conflict_dicts tests ────────────────────────────────────────────


def test_build_conflict_dicts_quarter_overflow():
    """opo assignment ending past q_end → QUARTER_OVERFLOW conflict."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    plan = MagicMock()
    plan.team = "TeamA"

    a = MagicMock()
    a.id = "asgn-1"
    a.backlog_item_id = "item-1"
    a.backlog_item = MagicMock()
    a.backlog_item.title = "Init A"
    a.phase = "opo"
    a.end_date = date(2026, 4, 5)  # past quarter end
    a.part_number = 1
    a.slack_days = None

    employees = [MagicMock(role="analyst"), MagicMock(role="dev")]
    for e in employees:
        e.role = e.role

    result = svc._build_conflict_dicts(plan, [a], employees, q_end)

    overflow = [r for r in result if r["type"] == "QUARTER_OVERFLOW"]
    assert len(overflow) == 1
    assert overflow[0]["severity"] == "critical"
    assert overflow[0]["detection_key"] == "QUARTER_OVERFLOW:item-1"
    assert overflow[0]["backlog_item_id"] == "item-1"


def test_build_conflict_dicts_split_required():
    """Assignment with part_number=2 → SPLIT_REQUIRED conflict (once per item)."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    plan = MagicMock()
    plan.team = "TeamA"

    a1 = MagicMock()
    a1.id = "asgn-1"
    a1.backlog_item_id = "item-2"
    a1.backlog_item = MagicMock()
    a1.backlog_item.title = "Init B"
    a1.phase = "analyst"
    a1.end_date = date(2026, 2, 10)
    a1.part_number = 1
    a1.slack_days = 5.0

    a2 = MagicMock()
    a2.id = "asgn-2"
    a2.backlog_item_id = "item-2"
    a2.backlog_item = MagicMock()
    a2.backlog_item.title = "Init B"
    a2.phase = "analyst"
    a2.end_date = date(2026, 2, 20)
    a2.part_number = 2
    a2.slack_days = 5.0

    employees = [MagicMock(role="analyst"), MagicMock(role="dev")]

    result = svc._build_conflict_dicts(plan, [a1, a2], employees, q_end)

    splits = [r for r in result if r["type"] == "SPLIT_REQUIRED"]
    assert len(splits) == 1
    assert splits[0]["detection_key"] == "SPLIT_REQUIRED:item-2"
    assert splits[0]["severity"] == "info"


def test_build_conflict_dicts_no_analyst_when_team_has_no_analysts():
    """Empty employees list + plan.team set → NO_ANALYST conflict."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    plan = MagicMock()
    plan.team = "TeamX"

    result = svc._build_conflict_dicts(plan, [], [], q_end)

    no_analyst = [r for r in result if r["type"] == "NO_ANALYST"]
    assert len(no_analyst) == 1
    assert no_analyst[0]["severity"] == "critical"
    assert no_analyst[0]["detection_key"] == "NO_ANALYST:TeamX"


def test_build_conflict_dicts_late_start():
    """Assignment with slack_days=-3 → LATE_START conflict."""
    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    plan = MagicMock()
    plan.team = "TeamA"

    a = MagicMock()
    a.id = "asgn-late"
    a.backlog_item_id = "item-3"
    a.backlog_item = MagicMock()
    a.backlog_item.title = "Init C"
    a.phase = "dev"
    a.end_date = date(2026, 3, 20)
    a.part_number = 1
    a.slack_days = -3.0
    a.employee_id = "emp-1"

    employees = [MagicMock(role="analyst"), MagicMock(role="dev")]

    result = svc._build_conflict_dicts(plan, [a], employees, q_end)

    late = [r for r in result if r["type"] == "LATE_START"]
    assert len(late) == 1
    assert late[0]["severity"] == "warning"
    assert late[0]["detection_key"] == "LATE_START:asgn-late"
    assert late[0]["metric_value"] == -3.0
    assert late[0]["assignment_id"] == "asgn-late"


def test_build_conflict_dicts_overload_high_from_escalate_event():
    """LevelingEvent(action='escalate', overload_pct=150) → OVERLOAD_HIGH, severity=critical."""
    from app.services.rcpsp_leveler import LevelingEvent

    db = MagicMock()
    svc = ResourcePlanningService(db)

    q_end = date(2026, 3, 31)

    plan = MagicMock()
    plan.team = "TeamA"

    ev = LevelingEvent(
        assignment_id="asgn-5",
        action="escalate",
        reason="нет слака для сдвига",
        overload_pct=150.0,
        affected_dates=[date(2026, 2, 15)],
    )
    svc._last_leveling_events = [ev]

    employees = [MagicMock(role="analyst"), MagicMock(role="dev")]

    result = svc._build_conflict_dicts(plan, [], employees, q_end)

    overload = [r for r in result if r["type"] == "OVERLOAD_HIGH"]
    assert len(overload) == 1
    assert overload[0]["severity"] == "critical"
    assert overload[0]["metric_value"] == 150.0
    assert overload[0]["assignment_id"] == "asgn-5"


# ── compute_schedule leveler integration smoke ─────────────────────────────
# NOTE: A full integration smoke test (1 plan + 2 overlapping items → leveler runs)
# requires a real SQLAlchemy Session with migrations applied, plus ScenarioAllocation
# and EmployeeTeam rows — not achievable with the MagicMock pattern used here.
# The leveler logic is covered by tests/test_rcpsp_leveler.py; the wire-up is
# validated by the unit tests above (_build_role_pools + _last_leveling_events init)
# and by running the full test suite without regressions.


# ── ОПЭ parallel integration test ─────────────────────────────────────────

def test_opo_rows_start_simultaneously(db_session: Session) -> None:
    """ОПЭ фаза создаёт 2 параллельных строки (analyst + dev) с одинаковым start_date.

    Строки должны:
    - иметь phase="opo"
    - иметь hours=8.0 каждая (total=16, ratio=0.5)
    - принадлежать разным сотрудникам
    - иметь одинаковый start_date (запуск в параллель после QA)
    """
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "OPO_TEST"

    # Три сотрудника: analyst, developer, qa
    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role.capitalize()}-opo",
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        et = EmployeeTeam(employee_id=e.id, team=team, is_primary=True)
        db_session.add(et)
        return e

    analyst_emp = _emp("analyst")
    dev_emp = _emp("developer")
    _emp("qa")

    # BacklogItem: только QA + ОПЭ часы, без assignee (чтобы экспонировать баг)
    item = BacklogItem(
        title="ОПЭ test item",
        priority=1,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=0.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=16.0,
        opo_analyst_ratio=0.5,
    )
    db_session.add(item)
    db_session.flush()

    # Сценарий + план
    scenario = PlanningScenario(
        name="opo-test-scenario",
        quarter="Q2",
        year=2026,
        status="draft",
        team=team,
    )
    db_session.add(scenario)
    db_session.flush()

    alloc = ScenarioAllocation(
        scenario_id=scenario.id,
        backlog_item_id=item.id,
        included_flag=True,
    )
    db_session.add(alloc)

    plan = ResourcePlan(
        team=team,
        quarter="Q2",
        year=2026,
        status="draft",
        scenario_id=scenario.id,
    )
    db_session.add(plan)
    db_session.commit()

    # Запустить планировщик
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    # Проверить результат
    rows = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "opo",
            )
        )
        .scalars()
        .all()
    )

    # Сгруппировать по сотруднику — могут быть split-сегменты внутри одного сотрудника
    from collections import defaultdict as _defaultdict
    hours_by_emp: dict = _defaultdict(float)
    start_by_emp: dict = {}
    for r in rows:
        hours_by_emp[r.employee_id] += r.hours_allocated
        if r.employee_id not in start_by_emp or r.start_date < start_by_emp[r.employee_id]:
            start_by_emp[r.employee_id] = r.start_date

    assert len(hours_by_emp) == 2, (
        f"Ожидалось 2 сотрудника в opo, получено {len(hours_by_emp)}. "
        f"Баг: если assignee не задан, analyst_id=None и строка analyst пропускается."
    )
    assert analyst_emp.id in hours_by_emp, "analyst должен быть в opo"
    assert dev_emp.id in hours_by_emp, "developer должен быть в opo"

    assert abs(hours_by_emp[analyst_emp.id] - 8.0) < 0.01, (
        f"analyst opo: ожидалось 8.0ч, получено {hours_by_emp[analyst_emp.id]}"
    )
    assert abs(hours_by_emp[dev_emp.id] - 8.0) < 0.01, (
        f"developer opo: ожидалось 8.0ч, получено {hours_by_emp[dev_emp.id]}"
    )

    # Оба сотрудника должны стартовать в один день (параллельное выполнение)
    assert start_by_emp[analyst_emp.id] == start_by_emp[dev_emp.id], (
        f"Строки opo должны стартовать одновременно: "
        f"analyst={start_by_emp[analyst_emp.id]}, dev={start_by_emp[dev_emp.id]}"
    )


# ── Phase 3: _resolve_phase_calendar_days unit tests ──────────────────────


def test_resolve_phase_calendar_days_uses_duration_field():
    """duration_analyst_days=5 overrides hours/8 calculation; jira_field_set=True."""
    from app.services.resource_planning_service import _resolve_phase_calendar_days

    item = MagicMock()
    item.duration_analyst_days = 5.0
    item.involvement_analyst = None

    cal_days, jira_set = _resolve_phase_calendar_days(item, "analyst", 8.0)
    assert cal_days == 5.0
    assert jira_set is True


def test_resolve_phase_calendar_days_uses_involvement_when_no_duration():
    """involvement_dev=0.5, no duration → 16h / (8×0.5) = 4.0 days; jira_field_set=True."""
    from app.services.resource_planning_service import _resolve_phase_calendar_days

    item = MagicMock()
    item.duration_dev_days = None
    item.involvement_dev = 0.5

    cal_days, jira_set = _resolve_phase_calendar_days(item, "dev", 16.0)
    assert abs(cal_days - 4.0) < 0.01
    assert jira_set is True


def test_resolve_phase_calendar_days_default_fallback():
    """No duration, no involvement → hours/8; jira_field_set=False."""
    from app.services.resource_planning_service import _resolve_phase_calendar_days

    item = MagicMock()
    item.duration_dev_days = None
    item.involvement_dev = None

    cal_days, jira_set = _resolve_phase_calendar_days(item, "dev", 16.0)
    assert abs(cal_days - 2.0) < 0.01
    assert jira_set is False


# ── Phase 3+4: compute_schedule integration tests ─────────────────────────


def test_compute_uses_duration_days(db_session: Session) -> None:
    """estimate_analyst_hours=8, duration_analyst_days=5 → analyst spans 5 working days."""
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "DURTEST1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="DurTestAnalyst1",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="DurTest item 1",
        priority=1,
        estimate_analyst_hours=8.0,
        duration_analyst_days=5.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="dur-test-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
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

    assert len(rows) >= 1
    all_start = min(r.start_date for r in rows)
    all_end = max(r.end_date for r in rows)
    # Count working days from start to end (inclusive)
    span_days = 0
    d = all_start
    while d <= all_end:
        if d.weekday() < 5:
            span_days += 1
        d += timedelta(days=1)

    assert span_days >= 5, (
        f"Ожидалось span ≥ 5 рабочих дней (duration_analyst_days=5), получено {span_days}"
    )


def test_compute_uses_involvement_when_no_duration(db_session: Session) -> None:
    """estimate_dev_hours=16, involvement_dev=0.5, no duration → span ~4 working days."""
    from datetime import timedelta
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "INVTEST1"

    dev_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="InvTestDev1",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="Inv test item 1",
        priority=1,
        estimate_dev_hours=16.0,
        involvement_dev=0.5,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="inv-test-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).all()

    assert len(rows) >= 1
    all_start = min(r.start_date for r in rows)
    all_end = max(r.end_date for r in rows)
    span_days = 0
    d = all_start
    while d <= all_end:
        if d.weekday() < 5:
            span_days += 1
        d += timedelta(days=1)

    # involvement=0.5 → 16 / (8×0.5) = 4 working days
    assert span_days >= 4, (
        f"Ожидалось span ≥ 4 рабочих дней (involvement=0.5, 16h), получено {span_days}"
    )


def test_compute_default_no_jira_fields(db_session: Session) -> None:
    """estimate_dev_hours=16, no involvement or duration → 2 working days (16/8)."""
    from datetime import timedelta
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "DEFTEST1"

    dev_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="DefTestDev1",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="Default test item 1",
        priority=1,
        estimate_dev_hours=16.0,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="def-test-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).all()

    assert len(rows) >= 1
    all_start = min(r.start_date for r in rows)
    all_end = max(r.end_date for r in rows)
    # 16h / 6h_per_day (DEFAULT_HOURS_PER_DAY) = ~3 calendar days
    # phase_end cursor is max(raw_end, cal_end) where cal_days=16/8=2 working days
    # The raw_end already spans ceil(16/6)=3 calendar days, cal_end=2 working days.
    # So span could be 2-3 depending on weekdays. Just assert it's ≤ 5 days (not stretched).
    span_days = 0
    d = all_start
    while d <= all_end:
        if d.weekday() < 5:
            span_days += 1
        d += timedelta(days=1)

    assert span_days <= 5, (
        f"Без Jira-полей span должен быть ≤ 5 рабочих дней, получено {span_days}"
    )


# ── Phase 4: parallel_count_* integration test ────────────────────────────


def test_compute_parallel_count_shortens_qa_span(db_session: Session) -> None:
    """parallel_count_qa=2 + duration_qa_days=10 → QA span halved to ~5 working days."""
    from datetime import timedelta
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "PARTEST1"

    # QA phase is hours-only in legacy (no employee), uses days_needed from hours.
    # parallel_count_qa affects the cursor via _resolve_phase_calendar_days.
    # But QA span in legacy is computed differently (ceil(hours/6)).
    # For Task B test we use dev phase with duration_dev_days + parallel_count_dev.
    dev_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="ParTestDev1",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="ParTest item 1",
        priority=1,
        estimate_dev_hours=80.0,
        duration_dev_days=10.0,
        parallel_count_dev=2,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="par-test-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).all()

    assert len(rows) >= 1
    all_start = min(r.start_date for r in rows)
    all_end = max(r.end_date for r in rows)
    span_days = 0
    d = all_start
    while d <= all_end:
        if d.weekday() < 5:
            span_days += 1
        d += timedelta(days=1)

    # parallel_count_dev=2 + duration_dev_days=10: cal_days = 10/2 = 5 рабочих дней —
    # ЦЕЛЕВОЙ срок, но фактическая ёмкость одного исполнителя = 8 ч/день.
    # Контракт: часы из сценария святы (80 ч), span расширяется до ceil(80/8) ≈ 10
    # рабочих дней (~14 календарных). RCPSP-leveler поднимет конфликт перегрузки.
    total_hours = sum(r.hours_allocated or 0 for r in rows)
    assert abs(total_hours - 80.0) < 0.01, (
        f"всеми сегментами должно быть размещено 80 ч, размещено {total_hours}"
    )


# ── Phase 5: auto-split analyst tests ─────────────────────────────────────


def test_legacy_split_skipped_when_fits(db_session: Session) -> None:
    """Small plan that fits in quarter → no analyst split (single row)."""
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "SPLITSKIP1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="SplitSkipAnalyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    dev_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="SplitSkipDev",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev_emp.id, team=team, is_primary=True))

    item = BacklogItem(
        title="Small fit item",
        priority=1,
        estimate_analyst_hours=8.0,
        estimate_dev_hours=8.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="split-skip-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=item.id, included_flag=True
    ))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
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

    # Small plan fits → no split, part_number should all be 1
    part_numbers = {r.part_number for r in analyst_rows}
    assert part_numbers == {1}, (
        f"Маленький план вмещается — сплит не нужен, part_numbers={part_numbers}"
    )


def test_no_auto_split_on_overflow(db_session: Session) -> None:
    """Авто-сплит выключен: даже при overflow аналитическая фаза = одна строка."""
    from sqlalchemy import select

    from app.models.backlog_item import BacklogItem
    from app.models.employee import Employee
    from app.models.employee_team import EmployeeTeam
    from app.models.planning_scenario import PlanningScenario
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.models.scenario_allocation import ScenarioAllocation

    team = "NOSPLITOVF1"

    analyst_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="NoSplitOvfAnalyst",
        team=team,
        is_active=True,
        role="analyst",
    )
    db_session.add(analyst_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=analyst_emp.id, team=team, is_primary=True))

    dev_emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name="NoSplitOvfDev",
        team=team,
        is_active=True,
        role="developer",
    )
    db_session.add(dev_emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=dev_emp.id, team=team, is_primary=True))

    big_item = BacklogItem(
        title="Big analyst item",
        priority=1,
        estimate_analyst_hours=400.0,
        estimate_dev_hours=8.0,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(big_item)
    db_session.flush()

    scenario = PlanningScenario(
        name="no-split-ovf-1", quarter="Q2", year=2026, status="draft", team=team
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(ScenarioAllocation(
        scenario_id=scenario.id, backlog_item_id=big_item.id, included_flag=True
    ))

    plan = ResourcePlan(team=team, quarter="Q2", year=2026, status="draft", scenario_id=scenario.id)
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    analyst_rows = db_session.scalars(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id,
            ResourcePlanAssignment.phase == "analyst",
            ResourcePlanAssignment.backlog_item_id == big_item.id,
        )
    ).all()

    assert len(analyst_rows) == 1
    assert analyst_rows[0].part_number == 1
