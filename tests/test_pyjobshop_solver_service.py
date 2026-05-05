"""Unit tests for PyJobShopSolverService на синтетических данных."""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.models.employee import Employee
from app.models.backlog_item import BacklogItem
from app.models.plan_item_dependency import PlanItemDependency
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.scheduled_block import ScheduledBlock
from app.services.pyjobshop_solver_service import PyJobShopSolverService


def _make_employee(db: Session, role: str, team: str = "A") -> Employee:
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:16],
        display_name=f"{role.capitalize()}1",
        team=team,
        is_active=True,
        role=role,
    )
    db.add(emp)
    db.flush()
    return emp


@pytest.fixture
def simple_plan(db_session: Session):
    """1 сотрудник-разработчик, 1 backlog с phase=dev на 16ч → 2 рабочих дня."""
    emp = _make_employee(db_session, role="developer", team="A")

    item = BacklogItem(
        title="Story 1",
        priority=1,
        estimate_dev_hours=16.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="A", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=16.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
    )
    db_session.add(assignment)
    db_session.commit()
    return {"plan": plan, "employee": emp, "item": item, "assignment": assignment}


def test_solver_assigns_dev_to_developer(simple_plan, db_session: Session):
    plan = simple_plan["plan"]
    emp = simple_plan["employee"]

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    # Один dev на эту задачу — должен быть назначен наш единственный разработчик
    assert a["assignee_employee_id"] == emp.id


def test_solver_respects_employee_absence(db_session: Session):
    """Задача не может стартовать в период отсутствия сотрудника."""
    # Q2 2026 starts 2026-04-01; employee is absent 2026-04-01 – 2026-04-15
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name="DevAbsent",
        team="B",
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    # Получаем или создаём причину отсутствия
    reason = db_session.scalars(
        select(AbsenceReason).where(AbsenceReason.code == "vacation")
    ).first()
    if reason is None:
        reason = AbsenceReason(code="vacation", label="Отпуск")
        db_session.add(reason)
        db_session.flush()

    absence = Absence(
        employee_id=emp.id,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 15),
        reason_id=reason.id,
    )
    db_session.add(absence)
    db_session.flush()

    item = BacklogItem(
        title="Task After Absence",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="B", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 16),
        end_date=date(2026, 4, 16),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача должна стартовать ПОСЛЕ окончания отпуска (2026-04-15)
    assert a["start_date"] >= date(2026, 4, 16)


def test_solver_respects_employee_blocked_zone(db_session: Session):
    """Задача не стартует в заблокированный период (employee-scope ScheduledBlock)."""
    # Q2 2026 starts 2026-04-01; blocked 2026-04-01 – 2026-04-10 (закрытие месяца).
    # Первый доступный рабочий день после блока: 2026-04-13 (пн, т.к. 11-12 — выходные).
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name="DevBlocked",
        team="C",
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    block = ScheduledBlock(
        employee_id=emp.id,
        team=None,
        role_id=None,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
        reason="Закрытие месяца",
    )
    db_session.add(block)
    db_session.flush()

    item = BacklogItem(
        title="Task After Block",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="C", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 13),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача должна стартовать не раньше 2026-04-13 (первый рабочий день после блока)
    assert a["start_date"] >= date(2026, 4, 13)


def test_solver_respects_fs_dependency(db_session: Session):
    """Задача B с зависимостью FS от A должна стартовать не раньше окончания A."""
    emp = _make_employee(db_session, role="developer", team="E")

    item_a = BacklogItem(
        title="Item A",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    item_b = BacklogItem(
        title="Item B",
        priority=2,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add_all([item_a, item_b])
    db_session.flush()

    plan = ResourcePlan(team="E", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assign_a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item_a.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 1),
    )
    assign_b = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item_b.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 2),
        end_date=date(2026, 4, 2),
    )
    db_session.add_all([assign_a, assign_b])
    db_session.flush()

    dep = PlanItemDependency(
        plan_id=plan.id,
        from_item_id=item_a.id,
        to_item_id=item_b.id,
        dep_type="FS",
        lag_days=0,
        source="manual",
    )
    db_session.add(dep)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assignments = {a["backlog_item_id"]: a for a in result["assignments"]}
    assert item_a.id in assignments
    assert item_b.id in assignments
    # B должен стартовать не раньше окончания A
    assert assignments[item_b.id]["start_date"] >= assignments[item_a.id]["end_date"]


def test_solver_respects_pinned_assignment(db_session: Session):
    """Закреплённый (is_pinned) исполнитель не должен быть переназначен."""
    emp_x = _make_employee(db_session, role="developer", team="F")
    emp_y = _make_employee(db_session, role="developer", team="F")

    item = BacklogItem(
        title="Pinned Item",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="F", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 1),
        employee_id=emp_x.id,
        is_pinned=True,
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    # Закреплённый исполнитель должен сохраниться
    assert a["assignee_employee_id"] == emp_x.id


def test_solver_prefers_higher_priority(db_session: Session):
    """Задача с приоритетом 1 должна стартовать раньше, чем с приоритетом 10."""
    emp = _make_employee(db_session, role="developer", team="G")

    item_hi = BacklogItem(
        title="High Priority",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    item_lo = BacklogItem(
        title="Low Priority",
        priority=10,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add_all([item_hi, item_lo])
    db_session.flush()

    plan = ResourcePlan(team="G", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assign_hi = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item_hi.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 1),
    )
    assign_lo = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item_lo.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 2),
        end_date=date(2026, 4, 2),
    )
    db_session.add_all([assign_hi, assign_lo])
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assignments = {a["backlog_item_id"]: a for a in result["assignments"]}
    assert item_hi.id in assignments
    assert item_lo.id in assignments
    # Высокоприоритетная задача должна стартовать раньше низкоприоритетной
    assert assignments[item_hi.id]["start_date"] <= assignments[item_lo.id]["start_date"]


def test_solver_respects_team_wide_block(db_session: Session):
    """Team-wide ScheduledBlock (employee_id=None, role_id=None) блокирует сотрудника."""
    # Блок на всю команду D: 2026-04-01 – 2026-04-10.
    emp = Employee(
        jira_account_id=uuid.uuid4().hex[:8],
        display_name="DevTeamBlock",
        team="D",
        is_active=True,
        role="developer",
    )
    db_session.add(emp)
    db_session.flush()

    block = ScheduledBlock(
        employee_id=None,
        role_id=None,
        team="D",
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 10),
        reason="Командный мораторий",
    )
    db_session.add(block)
    db_session.flush()

    item = BacklogItem(
        title="Task After Team Block",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="D", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 13),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача должна стартовать не раньше 2026-04-13 (первый рабочий день после блока)
    assert a["start_date"] >= date(2026, 4, 13)



def test_solver_skill_match_is_exact(db_session):
    """Сотрудник с ролью developer-lead НЕ подходит под phase=dev."""
    import uuid
    from datetime import date
    from app.models.employee import Employee
    from app.models.backlog_item import BacklogItem
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.services.pyjobshop_solver_service import PyJobShopSolverService

    lead = Employee(jira_account_id=uuid.uuid4().hex[:16], display_name="Lead", team="SK", is_active=True, role="developer-lead")
    db_session.add(lead); db_session.flush()
    item = BacklogItem(title="Dev work", priority=1, estimate_dev_hours=8.0, estimate_analyst_hours=0.0, estimate_qa_hours=0.0, estimate_opo_hours=0.0)
    db_session.add(item); db_session.flush()
    plan = ResourcePlan(team="SK", quarter="Q2", year=2026, status="draft")
    db_session.add(plan); db_session.flush()
    db_session.add(ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item.id, phase="dev", hours_allocated=8.0, start_date=date(2026,4,1), end_date=date(2026,4,1)))
    db_session.commit()
    result = PyJobShopSolverService(db_session).solve(plan.id)
    assert item.id in result["infeasible_items"]
    assert all(a.get("assignee_employee_id") != lead.id for a in result["assignments"])


def test_solver_main_assignee_prefers_analyst_phase(db_session):
    """Multi-phase: analyst главный даже если QA длиннее."""
    from datetime import date
    from app.models.backlog_item import BacklogItem
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.services.pyjobshop_solver_service import PyJobShopSolverService

    analyst = _make_employee(db_session, role="analyst", team="MP")
    qa = _make_employee(db_session, role="qa", team="MP")
    item = BacklogItem(title="Multi", priority=1, estimate_analyst_hours=8.0, estimate_dev_hours=0.0, estimate_qa_hours=40.0, estimate_opo_hours=0.0)
    db_session.add(item); db_session.flush()
    plan = ResourcePlan(team="MP", quarter="Q2", year=2026, status="draft")
    db_session.add(plan); db_session.flush()
    db_session.add_all([
        ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item.id, phase="analyst", hours_allocated=8.0, start_date=date(2026,4,1), end_date=date(2026,4,1)),
        ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item.id, phase="qa", hours_allocated=40.0, start_date=date(2026,4,2), end_date=date(2026,4,7)),
    ])
    db_session.commit()
    result = PyJobShopSolverService(db_session).solve(plan.id)
    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    matching = [a for a in result["assignments"] if a["backlog_item_id"] == item.id]
    assert len(matching) == 1
    assert matching[0]["assignee_employee_id"] == analyst.id
    assert matching[0]["assignee_employee_id"] != qa.id


def test_solver_keeps_opo_parallel(db_session: Session):
    """Два opo-ряда (analyst + dev) с pre-assigned исполнителями запускаются параллельно.

    Оба ряда помечены is_pinned=True, что заставляет солвер использовать именно
    указанного сотрудника. Ожидаем: оба scheduled, start_date расходятся не более
    чем на 1 день (параллельное исполнение, не последовательное).
    """
    analyst_emp = _make_employee(db_session, role="analyst", team="OPO_S")
    dev_emp = _make_employee(db_session, role="developer", team="OPO_S")

    item = BacklogItem(
        title="OPO Parallel Item",
        priority=1,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=16.0,
        opo_analyst_ratio=0.5,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="OPO_S", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    # Оба ряда pinned к конкретным сотрудникам, обоим стартовать в один день
    opo_start = date(2026, 4, 7)  # Понедельник Q2 2026
    assign_analyst = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="opo",
        hours_allocated=8.0,
        start_date=opo_start,
        end_date=opo_start,
        employee_id=analyst_emp.id,
        is_pinned=True,
    )
    assign_dev = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="opo",
        hours_allocated=8.0,
        start_date=opo_start,
        end_date=opo_start,
        employee_id=dev_emp.id,
        is_pinned=True,
    )
    db_session.add_all([assign_analyst, assign_dev])
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    # Оба ряда должны быть в phase_breakdown
    assert len(result["assignments"]) == 1
    breakdown = result["assignments"][0]["phase_breakdown"]
    opo_rows = [p for p in breakdown if p["phase"] == "opo"]
    assert len(opo_rows) == 2, f"Ожидалось 2 opo-строки в breakdown, получено {len(opo_rows)}"

    # Оба сотрудника назначены
    assigned_emps = {p["employee_id"] for p in opo_rows}
    assert analyst_emp.id in assigned_emps, "analyst должен быть в opo breakdown"
    assert dev_emp.id in assigned_emps, "developer должен быть в opo breakdown"

    # Параллельность: start_date обоих ряд расходится не более чем на 1 день
    start_dates = [p["start_date"] for p in opo_rows]
    date_spread = abs((start_dates[0] - start_dates[1]).days)
    assert date_spread <= 1, (
        f"Строки opo должны стартовать одновременно (≤1 день разницы), "
        f"получено: {start_dates}"
    )


def _count_working_days(start: date, end: date) -> int:
    """Число рабочих дней (пн-пт) в диапазоне [start, end] включительно."""
    count = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            count += 1
        d += timedelta(days=1)
    return count


def test_solver_uses_jira_duration(db_session: Session):
    """Солвер использует duration_analyst_days=4 из BacklogItem, игнорируя hours_allocated=16.

    При involvement=0.5 и duration=4 дня задача должна занять ~4 рабочих дня,
    а не 2 (как было бы при старом поведении: 16ч / 8 = 2 дня).
    """
    emp = _make_employee(db_session, role="analyst", team="JD1")

    item = BacklogItem(
        title="JiraDuration Item",
        priority=1,
        estimate_analyst_hours=16.0,
        estimate_dev_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        involvement_analyst=0.5,
        duration_analyst_days=4.0,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="JD1", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="analyst",
        hours_allocated=16.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 2),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    # Span должен быть ≥ 3 рабочих дня (duration=4 дня × 8 slots / 4 demand_per_slot)
    working_days = _count_working_days(a["start_date"], a["end_date"])
    assert working_days >= 3, (
        f"Ожидали ≥3 рабочих дня (duration_analyst_days=4), получили {working_days} "
        f"({a['start_date']} – {a['end_date']})"
    )


def test_solver_parallel_via_involvement(db_session: Session):
    """Два BacklogItem с involvement=0.4 планируются параллельно у одного сотрудника.

    0.4 + 0.4 = 0.8 ≤ 1.0 — оба укладываются в рабочий день одновременно,
    поэтому start_date второй задачи не должен быть отложен на следующую неделю.
    """
    emp = _make_employee(db_session, role="analyst", team="PAR1")

    item1 = BacklogItem(
        title="Parallel Item 1",
        priority=1,
        estimate_analyst_hours=20.0,
        estimate_dev_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        involvement_analyst=0.4,
        duration_analyst_days=5.0,
    )
    item2 = BacklogItem(
        title="Parallel Item 2",
        priority=1,
        estimate_analyst_hours=20.0,
        estimate_dev_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        involvement_analyst=0.4,
        duration_analyst_days=5.0,
    )
    db_session.add_all([item1, item2])
    db_session.flush()

    plan = ResourcePlan(team="PAR1", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    db_session.add_all([
        ResourcePlanAssignment(
            plan_id=plan.id,
            backlog_item_id=item1.id,
            phase="analyst",
            hours_allocated=20.0,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
        ),
        ResourcePlanAssignment(
            plan_id=plan.id,
            backlog_item_id=item2.id,
            phase="analyst",
            hours_allocated=20.0,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
        ),
    ])
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 2

    starts = sorted(a["start_date"] for a in result["assignments"])
    # При параллельном исполнении start_date расходятся не более чем на 1 день
    spread = (starts[-1] - starts[0]).days
    assert spread <= 1, (
        f"Задачи с involvement=0.4 должны исполняться параллельно (≤1 день разницы), "
        f"получили start_dates: {starts}"
    )


def test_solver_default_involvement_unchanged(db_session: Session):
    """BacklogItem без involvement/duration ведёт себя как раньше.

    Регрессия: hours_allocated=8, нет involvement → duration_slots=8,
    demand=8 → задача занимает 1 рабочий день у разработчика.
    """
    emp = _make_employee(db_session, role="developer", team="REG1")

    item = BacklogItem(
        title="Default Behavior",
        priority=1,
        estimate_dev_hours=8.0,
        estimate_analyst_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        # involvement_dev и duration_dev_days не заданы — None
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="REG1", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        hours_allocated=8.0,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 1),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    assert a["assignee_employee_id"] == emp.id
    # Задача назначена и span разумный (≤ 3 рабочих дня для 8ч задачи).
    # PyJobShop возвращает end=start+duration (включительно), поэтому 8-часовая
    # задача (1 рабочий день) может дать span в 2 дня по slot_to_date арифметике.
    working_days = _count_working_days(a["start_date"], a["end_date"])
    assert working_days <= 3, (
        f"Ожидали ≤3 рабочих дня для 8ч задачи, получили {working_days}"
    )


import pytest as _pytest


@_pytest.mark.skip(reason="F6 lag_days откатан — SIGSEGV в OR-Tools/Windows")
def test_solver_fs_dependency_respects_lag_days(db_session):
    """FS lag_days=2 → B стартует не раньше end_a + 2 дня."""
    from datetime import date
    from app.models.backlog_item import BacklogItem
    from app.models.plan_item_dependency import PlanItemDependency
    from app.models.resource_plan import ResourcePlan
    from app.models.resource_plan_assignment import ResourcePlanAssignment
    from app.services.pyjobshop_solver_service import PyJobShopSolverService

    emp = _make_employee(db_session, role="developer", team="LG")
    item_a = BacklogItem(title="A", priority=1, estimate_dev_hours=8.0, estimate_analyst_hours=0.0, estimate_qa_hours=0.0, estimate_opo_hours=0.0)
    item_b = BacklogItem(title="B", priority=2, estimate_dev_hours=8.0, estimate_analyst_hours=0.0, estimate_qa_hours=0.0, estimate_opo_hours=0.0)
    db_session.add_all([item_a, item_b]); db_session.flush()
    plan = ResourcePlan(team="LG", quarter="Q2", year=2026, status="draft")
    db_session.add(plan); db_session.flush()
    db_session.add_all([
        ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item_a.id, phase="dev", hours_allocated=8.0, start_date=date(2026,4,1), end_date=date(2026,4,1)),
        ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item_b.id, phase="dev", hours_allocated=8.0, start_date=date(2026,4,2), end_date=date(2026,4,2)),
    ])
    db_session.flush()
    db_session.add(PlanItemDependency(plan_id=plan.id, from_item_id=item_a.id, to_item_id=item_b.id, dep_type="FS", lag_days=2, source="manual"))
    db_session.commit()
    result = PyJobShopSolverService(db_session).solve(plan.id)
    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assignments = {a["backlog_item_id"]: a for a in result["assignments"]}
    end_a = assignments[item_a.id]["end_date"]
    start_b = assignments[item_b.id]["start_date"]
    delta_days = (start_b - end_a).days
    assert delta_days >= 2, f"delta={delta_days}"


def test_solver_parallel_count_qa_halves_duration(db_session: Session):
    """BacklogItem.parallel_count_qa=2 сокращает span фазы QA вдвое.

    duration_qa_days=4 с parallel_count_qa=2 → duration_slots=16 (~2 рабочих дня, ≤3 с запасом).
    """
    emp = _make_employee(db_session, role="qa", team="PC1")

    item = BacklogItem(
        title="Parallel QA Item",
        priority=1,
        estimate_qa_hours=32.0,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=0.0,
        estimate_opo_hours=0.0,
        duration_qa_days=4.0,
        parallel_count_qa=2,
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="PC1", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="qa",
        hours_allocated=32.0,
        start_date=date(2026, 4, 7),
        end_date=date(2026, 4, 9),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    working_days = _count_working_days(a["start_date"], a["end_date"])
    assert working_days <= 3, (
        f"parallel_count_qa=2 должен уложить 4-дневную QA в ≤3 рабочих дня, "
        f"получили {working_days} ({a['start_date']} – {a['end_date']})"
    )


def test_solver_parallel_count_inherits_from_project(db_session: Session):
    """parallel_count_qa=2 на Project, NULL на BacklogItem — наследуется.

    Поведение идентично явному заданию на уровне backlog item:
    duration_qa_days=4, N=2 → ≤3 рабочих дня.
    """
    from app.models.project import Project

    project = Project(
        jira_project_id="PC2_PROJ",
        key="PC2",
        name="PC2 Project",
        parallel_count_qa=2,
    )
    db_session.add(project)
    db_session.flush()

    emp = _make_employee(db_session, role="qa", team="PC2")

    item = BacklogItem(
        title="Inherit QA Item",
        priority=1,
        estimate_qa_hours=32.0,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=0.0,
        estimate_opo_hours=0.0,
        duration_qa_days=4.0,
        project_id=project.id,
        # parallel_count_qa не задан на item — должен взяться из project
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="PC2", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="qa",
        hours_allocated=32.0,
        start_date=date(2026, 4, 7),
        end_date=date(2026, 4, 9),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    working_days = _count_working_days(a["start_date"], a["end_date"])
    assert working_days <= 3, (
        f"project.parallel_count_qa=2 должен наследоваться и дать ≤3 рабочих дня, "
        f"получили {working_days} ({a['start_date']} – {a['end_date']})"
    )


def test_solver_parallel_count_default_one(db_session: Session):
    """Без parallel_count_qa span = полная duration_qa_days (нет ускорения).

    duration_qa_days=4, parallel_count не задан → span должен быть ≥3 рабочих дня.
    Для сравнения: с parallel_count_qa=2 было бы ≤2 рабочих дня.
    Используем небольшую длительность (≤5 дней), чтобы task влезал в одну рабочую неделю
    (solver non-preemptive, не может перешагнуть выходные mid-task).
    """
    emp = _make_employee(db_session, role="qa", team="PC3")

    item = BacklogItem(
        title="No Parallel QA",
        priority=1,
        estimate_qa_hours=32.0,
        estimate_analyst_hours=0.0,
        estimate_dev_hours=0.0,
        estimate_opo_hours=0.0,
        duration_qa_days=4.0,
        # parallel_count_qa не задан → N=1
    )
    db_session.add(item)
    db_session.flush()

    plan = ResourcePlan(team="PC3", quarter="Q2", year=2026, status="draft")
    db_session.add(plan)
    db_session.flush()

    assignment = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="qa",
        hours_allocated=32.0,
        start_date=date(2026, 4, 7),
        end_date=date(2026, 4, 10),
    )
    db_session.add(assignment)
    db_session.commit()

    result = PyJobShopSolverService(db_session).solve(plan.id)

    assert result["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert len(result["assignments"]) == 1
    a = result["assignments"][0]
    working_days = _count_working_days(a["start_date"], a["end_date"])
    assert working_days >= 3, (
        f"Без parallel_count_qa span должен быть ≥3 рабочих дня (duration_qa_days=4), "
        f"получили {working_days} ({a['start_date']} – {a['end_date']})"
    )
