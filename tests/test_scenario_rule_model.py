from app.models import ScenarioRule, PlanningScenario, MandatoryWorkType


def test_scenario_rule_create(db_session):
    sc = PlanningScenario(name="S"); db_session.add(sc); db_session.flush()
    wt = MandatoryWorkType(code="wt1", label="WT"); db_session.add(wt); db_session.flush()
    r = ScenarioRule(scenario_id=sc.id, role="analyst", work_type_id=wt.id, percent_of_norm=15.0)
    db_session.add(r); db_session.commit()
    assert db_session.query(ScenarioRule).filter_by(scenario_id=sc.id).count() == 1
