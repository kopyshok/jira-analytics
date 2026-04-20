"""Tests for PlanningScenario new fields: team, external_qa_hours."""
from app.models import PlanningScenario


def test_scenario_new_fields(db_session):
    s = PlanningScenario(name="T", team="TeamA", external_qa_hours=100.0)
    db_session.add(s)
    db_session.commit()
    fetched = db_session.query(PlanningScenario).filter_by(name="T").one()
    assert fetched.team == "TeamA"
    assert fetched.external_qa_hours == 100.0
    assert fetched.external_qa_hours is not None  # 0 is explicit
