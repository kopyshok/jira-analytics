from app.models import PhasePredecessor


def test_phase_predecessor_fields():
    pp = PhasePredecessor(
        successor_assignment_id="s-1",
        predecessor_assignment_id="p-1",
    )
    assert pp.successor_assignment_id == "s-1"
    assert pp.predecessor_assignment_id == "p-1"
