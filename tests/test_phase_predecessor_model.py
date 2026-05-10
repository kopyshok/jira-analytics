import pytest
from sqlalchemy.exc import IntegrityError

from app.models import PhasePredecessor


def test_phase_predecessor_fields():
    pp = PhasePredecessor(
        successor_assignment_id="s-1",
        predecessor_assignment_id="p-1",
    )
    assert pp.successor_assignment_id == "s-1"
    assert pp.predecessor_assignment_id == "p-1"


def test_phase_predecessor_unique_pair_constraint(db_session):
    """Duplicate (successor, predecessor) pair raises IntegrityError."""
    db_session.add(
        PhasePredecessor(
            successor_assignment_id="s-1",
            predecessor_assignment_id="p-1",
        )
    )
    db_session.commit()

    db_session.add(
        PhasePredecessor(
            successor_assignment_id="s-1",
            predecessor_assignment_id="p-1",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
