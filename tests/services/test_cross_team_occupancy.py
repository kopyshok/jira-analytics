"""Занятость сотрудников в опорных планах других команд."""

from datetime import date, datetime

from app.models import ResourcePlan, ResourcePlanAssignment
from app.services import cross_team_occupancy as cto
from tests.services.xteam_factory import add_item, book, make_employee, make_plan

D = date.fromisoformat


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


def _setup_booked(db_session):
    """Сотрудник E команды A занят в опорном плане A; M — сотрудник B."""
    e = make_employee(db_session, "Пряничников", "A")
    m = make_employee(db_session, "Свой B", "B")
    sc, plan = make_plan(db_session, "A")
    item = add_item(db_session, sc, "Задача A", dev=12)
    book(db_session, plan, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0})
    # Старая строка без посуточной раскладки: 9 ч на Чт, Пт, Пн.
    db_session.add(ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="analyst",
        employee_id=e.id, part_number=1, hours_allocated=9.0,
        start_date=D("2026-01-08"), end_date=D("2026-01-12"),
    ))
    db_session.commit()
    return e, m


def test_external_bookings_from_other_team(db_session):
    e, _m = _setup_booked(db_session)

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    )

    assert {b.team for b in bookings} == {"A"}
    assert all(b.provisional is False for b in bookings)
    assert cto.daily_totals(bookings) == {
        e.id: {
            D("2026-01-05"): 6.0, D("2026-01-06"): 6.0,
            D("2026-01-08"): 3.0, D("2026-01-09"): 3.0, D("2026-01-12"): 3.0,
        }
    }


def test_own_team_bookings_are_not_external(db_session):
    e, _m = _setup_booked(db_session)

    assert cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    ) == []


def test_external_bookings_cut_by_window(db_session):
    e, _m = _setup_booked(db_session)

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-06"), end=D("2026-01-06"),
    )

    assert cto.daily_totals(bookings) == {e.id: {D("2026-01-06"): 6.0}}


def test_subtract_occupancy():
    avail = {"e": {D("2026-01-05"): 6.0, D("2026-01-07"): 6.0}}
    occupied = {"e": {D("2026-01-05"): 4.0}, "x": {D("2026-01-05"): 9.0}}

    assert cto.subtract_occupancy(avail, occupied) == {
        "e": {D("2026-01-05"): 2.0, D("2026-01-07"): 6.0}
    }


def test_overlap_days_only_where_own_plan_works_inside_capacity():
    own = {D("2026-01-05"): 4.0, D("2026-01-07"): 2.0, D("2026-04-01"): 5.0}
    external = {D("2026-01-05"): 6.0, D("2026-01-06"): 6.0, D("2026-04-01"): 6.0}
    capacity = {D("2026-01-05"): 6.0, D("2026-01-06"): 6.0, D("2026-01-07"): 6.0}

    assert cto.overlap_days(own, external, capacity) == [D("2026-01-05")]


def test_borrowed_ids(db_session):
    e, m = _setup_booked(db_session)

    assert cto.borrowed_ids(
        db_session, "B", D("2026-01-01"), D("2026-03-31"), [e.id, m.id, None]
    ) == {e.id}
    assert cto.borrowed_ids(
        db_session, None, D("2026-01-01"), D("2026-03-31"), [e.id]
    ) == set()
