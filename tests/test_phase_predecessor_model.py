import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    BacklogItem,
    PhasePredecessor,
    ResourcePlan,
    ResourcePlanAssignment,
)


def test_phase_predecessor_fields():
    pp = PhasePredecessor(
        successor_assignment_id="s-1",
        predecessor_assignment_id="p-1",
    )
    assert pp.successor_assignment_id == "s-1"
    assert pp.predecessor_assignment_id == "p-1"


def test_phase_predecessor_unique_pair_constraint(db_session):
    """Duplicate (successor, predecessor) pair raises IntegrityError."""
    # Реальные назначения: Postgres проверяет ссылки на них.
    plan = ResourcePlan(team="Команда А", quarter="Q2", year=2026, status="ready")
    item = BacklogItem(title="Инициатива")
    db_session.add_all([plan, item])
    db_session.flush()
    succ = ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item.id, phase="dev")
    pred = ResourcePlanAssignment(plan_id=plan.id, backlog_item_id=item.id, phase="analyst")
    db_session.add_all([succ, pred])
    db_session.flush()

    db_session.add(
        PhasePredecessor(
            successor_assignment_id=succ.id,
            predecessor_assignment_id=pred.id,
        )
    )
    db_session.commit()

    db_session.add(
        PhasePredecessor(
            successor_assignment_id=succ.id,
            predecessor_assignment_id=pred.id,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
