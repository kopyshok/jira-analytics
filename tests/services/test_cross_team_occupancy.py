"""Занятость сотрудников в опорных планах других команд."""

from datetime import datetime

from app.models import ResourcePlan
from app.services import cross_team_occupancy as cto
from tests.services.xteam_factory import make_plan


def test_reference_plan_prefers_ready_over_newer_stale(db_session):
    sc, ready = make_plan(db_session, "A", plan_status="ready",
                          computed_at=datetime(2026, 1, 1))
    stale = ResourcePlan(team="A", quarter="Q1", year=2026, status="stale",
                         scenario_id=sc.id, computed_at=datetime(2026, 1, 5))
    fork = ResourcePlan(team="A", quarter="Q1", year=2026, status="ready",
                        scenario_id=sc.id, computed_at=datetime(2026, 1, 9),
                        parent_plan_id=ready.id)
    db_session.add_all([stale, fork])
    db_session.commit()

    refs = cto.reference_plans(db_session, 2026, 1)

    assert refs["A"].plan_id == ready.id
    assert refs["A"].provisional is False


def test_reference_plan_prefers_baseline(db_session):
    sc, ready = make_plan(db_session, "B", plan_status="ready",
                          computed_at=datetime(2026, 1, 9))
    base = ResourcePlan(team="B", quarter="Q1", year=2026, status="stale",
                        scenario_id=sc.id, is_baseline=True)
    db_session.add(base)
    db_session.commit()

    assert cto.reference_plans(db_session, 2026, 1)["B"].plan_id == base.id


def test_reference_plan_falls_back_to_freshest_draft(db_session):
    make_plan(db_session, "C", scenario_status="draft",
              scenario_updated_at=datetime(2026, 1, 1))
    _, fresh = make_plan(db_session, "C", scenario_status="draft",
                         scenario_updated_at=datetime(2026, 2, 1))
    db_session.commit()

    ref = cto.reference_plans(db_session, 2026, 1)["C"]

    assert ref.plan_id == fresh.id
    assert ref.provisional is True


def test_reference_plan_approved_beats_draft_and_exclude_team(db_session):
    make_plan(db_session, "D", scenario_status="draft",
              scenario_updated_at=datetime(2026, 3, 1))
    _, approved = make_plan(db_session, "D", scenario_status="approved")
    make_plan(db_session, "E", quarter="1")  # квартал без буквы Q тоже находится
    db_session.commit()

    refs = cto.reference_plans(db_session, 2026, 1, exclude_team="E")

    assert refs["D"].plan_id == approved.id
    assert "E" not in refs
    assert "E" in cto.reference_plans(db_session, 2026, 1)


def test_quarter_num():
    assert cto.quarter_num("Q3") == 3
    assert cto.quarter_num("4") == 4
    assert cto.quarter_num(None) is None
    assert cto.quarter_num("Q9") is None
