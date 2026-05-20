"""После compute_schedule у инициативы с 4 фазами должны быть все рёбра:
analyst→dev, dev→qa, qa→opo (на обе строки opo).

Регрессия: даже если у инициативы уже было ребро analyst→dev (например, от
прошлого compute), пересчёт должен достроить qa→opo, а не пропускать
инициативу.
"""

import uuid

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
from app.services.resource_planning_service import ResourcePlanningService


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def relay_plan(db_session):
    """Команда из 2 сотрудников + одна инициатива со всеми 4 фазами."""
    team = "T_RELAY"

    def _emp(role: str) -> Employee:
        e = Employee(
            jira_account_id=uuid.uuid4().hex[:16],
            display_name=f"{role.capitalize()}-relay",
            team=team,
            is_active=True,
            role=role,
        )
        db_session.add(e)
        db_session.flush()
        db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
        return e

    analyst_emp = _emp("analyst")
    _emp("developer")

    item = BacklogItem(
        title="relay-test",
        priority=1,
        estimate_analyst_hours=8.0,
        estimate_dev_hours=16.0,
        estimate_qa_hours=8.0,
        estimate_opo_hours=8.0,
        opo_analyst_ratio=0.5,
        assignee_employee_id=analyst_emp.id,
    )
    db_session.add(item)
    db_session.flush()

    scenario = PlanningScenario(
        name="relay-scenario",
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
    return plan, item


# ---------------------------------------------------------------------------
# Test 1: Happy path — all edges present after fresh compute
# ---------------------------------------------------------------------------

def test_happy_path_all_edges_after_fresh_compute(db_session, relay_plan):
    """Первый compute создаёт все рёбра: analyst→dev, dev→qa, qa→opo."""
    plan, item = relay_plan

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    # Загружаем все рёбра для этого плана
    assignments = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.backlog_item_id == item.id,
            )
        )
        .scalars()
        .all()
    )
    by_phase = {}
    for a in assignments:
        by_phase.setdefault(a.phase, []).append(a)

    # Собираем все id назначений
    all_ids = {a.id for a in assignments}

    # Читаем все рёбра, где successor входит в этот план
    all_preds = (
        db_session.execute(
            select(PhasePredecessor).where(
                PhasePredecessor.successor_assignment_id.in_(all_ids)
            )
        )
        .scalars()
        .all()
    )

    # Строим set пар (succ_phase, pred_phase) по id → phase
    id_to_phase = {a.id: a.phase for a in assignments}
    phase_pairs = {
        (id_to_phase[pp.successor_assignment_id], id_to_phase[pp.predecessor_assignment_id])
        for pp in all_preds
        if pp.successor_assignment_id in id_to_phase and pp.predecessor_assignment_id in id_to_phase
    }

    assert ("dev", "analyst") in phase_pairs, "analyst→dev edge missing"
    assert ("qa", "dev") in phase_pairs, "dev→qa edge missing"
    assert ("opo", "qa") in phase_pairs, "qa→opo edge missing"


# ---------------------------------------------------------------------------
# Test 2: Regression — partial graph (only analyst→dev) gets qa→opo on recompute
# ---------------------------------------------------------------------------

def test_regression_partial_graph_gets_completed(db_session, relay_plan):
    """Регрессия: если первый compute создал только analyst→dev, следующий
    compute должен достроить qa→opo, а не пропустить инициативу целиком."""
    plan, item = relay_plan

    svc = ResourcePlanningService(db_session)
    # Первый compute — создаёт все рёбра и назначения
    svc.compute_schedule(plan.id)

    assignments = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.backlog_item_id == item.id,
            )
        )
        .scalars()
        .all()
    )
    by_phase = {}
    for a in assignments:
        by_phase.setdefault(a.phase, []).append(a)

    # Симулируем состояние «только analyst→dev создано, qa→opo отсутствует»:
    # удаляем все рёбра кроме analyst→dev.
    all_ids = {a.id for a in assignments}
    all_preds = (
        db_session.execute(
            select(PhasePredecessor).where(
                PhasePredecessor.successor_assignment_id.in_(all_ids)
            )
        )
        .scalars()
        .all()
    )

    id_to_phase = {a.id: a.phase for a in assignments}
    analyst_id = by_phase["analyst"][0].id
    dev_ids = {a.id for a in by_phase.get("dev", [])}

    # Удаляем все рёбра кроме analyst→dev
    for pp in all_preds:
        succ_phase = id_to_phase.get(pp.successor_assignment_id)
        pred_phase = id_to_phase.get(pp.predecessor_assignment_id)
        keep = (succ_phase == "dev" and pred_phase == "analyst")
        if not keep:
            db_session.delete(pp)
    db_session.commit()

    # Убеждаемся что qa→opo рёбра действительно удалены
    remaining = (
        db_session.execute(
            select(PhasePredecessor).where(
                PhasePredecessor.successor_assignment_id.in_(all_ids)
            )
        )
        .scalars()
        .all()
    )
    remaining_pairs = {
        (id_to_phase.get(pp.successor_assignment_id), id_to_phase.get(pp.predecessor_assignment_id))
        for pp in remaining
    }
    assert ("opo", "qa") not in remaining_pairs, "setup error: qa→opo should be absent"

    # Второй compute — должен достроить qa→opo
    svc.compute_schedule(plan.id)

    assignments2 = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.backlog_item_id == item.id,
            )
        )
        .scalars()
        .all()
    )
    all_ids2 = {a.id for a in assignments2}
    id_to_phase2 = {a.id: a.phase for a in assignments2}

    all_preds2 = (
        db_session.execute(
            select(PhasePredecessor).where(
                PhasePredecessor.successor_assignment_id.in_(all_ids2)
            )
        )
        .scalars()
        .all()
    )
    phase_pairs2 = {
        (id_to_phase2.get(pp.successor_assignment_id), id_to_phase2.get(pp.predecessor_assignment_id))
        for pp in all_preds2
        if pp.successor_assignment_id in id_to_phase2 and pp.predecessor_assignment_id in id_to_phase2
    }

    assert ("opo", "qa") in phase_pairs2, (
        "qa→opo edge missing after second compute — regression: early-exit skipped item because analyst→dev existed"
    )


# ---------------------------------------------------------------------------
# Test 3: User-touched — compute does NOT re-seed any edges for that item
# ---------------------------------------------------------------------------

def test_user_touched_item_not_reseeded(db_session, relay_plan):
    """Если predecessors_user_set=True хотя бы у одной фазы инициативы,
    compute не досевает никаких рёбер для неё."""
    plan, item = relay_plan

    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    assignments = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.backlog_item_id == item.id,
            )
        )
        .scalars()
        .all()
    )
    all_ids = {a.id for a in assignments}
    id_to_phase = {a.id: a.phase for a in assignments}

    # Удаляем все рёбра и выставляем predecessors_user_set на qa-фазе
    db_session.execute(
        PhasePredecessor.__table__.delete().where(
            PhasePredecessor.successor_assignment_id.in_(all_ids)
        )
    )
    qa_row = next(a for a in assignments if a.phase == "qa")
    qa_row.predecessors_user_set = True
    db_session.commit()

    # Третий compute — не должен досевать рёбра
    svc.compute_schedule(plan.id)

    assignments3 = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.backlog_item_id == item.id,
            )
        )
        .scalars()
        .all()
    )
    all_ids3 = {a.id for a in assignments3}
    all_preds3 = (
        db_session.execute(
            select(PhasePredecessor).where(
                PhasePredecessor.successor_assignment_id.in_(all_ids3)
            )
        )
        .scalars()
        .all()
    )

    assert len(all_preds3) == 0, (
        f"Expected no edges for user-touched item, got {len(all_preds3)}"
    )
