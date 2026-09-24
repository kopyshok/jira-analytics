"""База ресурса сценария вычитает часы, забронированные другими командами."""

from datetime import date

from app.models import EmployeeTeam, Team, TeamSubgroup
from app.services.resource_base_service import ResourceBaseService
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan


def _setup(db_session):
    """E состоит в A и в B (общий сотрудник); B бронирует его на 05.01."""
    e = make_employee(db_session, "Пряничников", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=6)
    book(db_session, plan_b, item_b, e, {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    db_session.commit()
    return e, sc_a


def test_daily_base_minus_other_team_bookings(db_session):
    e, sc_a = _setup(db_session)

    base = ResourceBaseService(db_session).compute(sc_a)

    emp = next(x for x in base.employees if x.employee_id == e.id)
    by_day = {d.date: d.hours for d in emp.days}
    assert by_day[date(2026, 1, 5)] == 2.0
    assert by_day[date(2026, 1, 6)] == 8.0


def test_summary_available_minus_bookings(db_session):
    e, sc_a = _setup(db_session)

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    assert s.booked_by_other_teams_by_role == {"developer": 6.0}
    assert s.available_by_role["developer"] == round(s.gross_by_role["developer"] - 6.0, 2)
    # Брутто не трогаем: брони вычитаются только из «На бэклог».
    assert s.gross_by_role["developer"] == s.calendar_gross_by_role["developer"]


def test_summary_ignores_bookings_outside_membership(db_session):
    e, sc_a = _setup(db_session)
    # В команде A только с 06.01 — бронь B на 05.01 приходится на день вне команды.
    db_session.query(EmployeeTeam).filter_by(employee_id=e.id, team="A").one().joined_at = date(2026, 1, 6)
    db_session.commit()

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    assert s.booked_by_other_teams_by_role == {}


def test_subgroup_capacity_loses_only_booked_member_hours(db_session):
    db_session.add(Team(id="t-a", name="A", has_subgroups=True))
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id="sg-x", team_id="t-a", name="X", sort_order=1),
        TeamSubgroup(id="sg-y", team_id="t-a", name="Y", sort_order=2),
    ])
    e, sc_a = _setup(db_session)
    g = make_employee(db_session, "Сосед", "A")
    for emp, sg in ((e, "sg-x"), (g, "sg-y")):
        db_session.query(EmployeeTeam).filter_by(employee_id=emp.id, team="A").one().subgroup_id = sg
    db_session.commit()

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    gross_x = s.gross_by_subgroup_role["sg-x"]["developer"]
    gross_y = s.gross_by_subgroup_role["sg-y"]["developer"]
    assert s.available_by_subgroup_role["sg-x"]["developer"] == round(gross_x - 6.0, 2)
    assert s.available_by_subgroup_role["sg-y"]["developer"] == gross_y


def test_resource_summary_endpoint_returns_booked_hours(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    _e, sc_a = _setup(db_session)

    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(f"/api/v1/planning/scenarios/{sc_a.id}/resource-summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["booked_by_other_teams_by_role"] == {"developer": 6.0}
    assert body["available_for_backlog_by_role"]["developer"] == round(
        body["total_by_role"]["developer"] - 6.0, 2
    )


def test_summary_booking_cut_matches_daily_base(db_session):
    """Бронь больше остатка дня после обязательных работ — сводка режет столько же, сколько база."""
    from app.models import MandatoryWorkType, ScenarioRule

    e, sc_a = _setup(db_session)  # бронь B: 6 ч на 05.01
    wt = MandatoryWorkType(code="xteam-meet", label="Совещания", subtracts_from_pool=True)
    db_session.add(wt)
    db_session.flush()
    db_session.add(ScenarioRule(
        scenario_id=sc_a.id, role="developer", work_type_id=wt.id, percent_of_norm=50.0,
    ))
    db_session.commit()
    svc = ResourceBaseService(db_session)

    base = svc.compute(sc_a)
    s = svc.compute_summary(sc_a)

    emp = next(x for x in base.employees if x.employee_id == e.id)
    # Норма 8 ч, половина — обязательные работы: на бэклог 4 ч; бронь съедает только их.
    assert {d.date: d.hours for d in emp.days}[date(2026, 1, 5)] == 0.0
    assert s.booked_by_other_teams_by_role == {"developer": 4.0}
    assert s.available_by_role["developer"] == emp.total_hours


def _setup_borrowed(db_session):
    """E — сотрудник A; команда B взяла его к себе (в B он не состоит)."""
    e = make_employee(db_session, "Шутов", "A")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=6), e,
         {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    db_session.commit()
    return e, sc_a


def test_daily_base_keeps_hours_borrowed_by_other_team(db_session):
    e, sc_a = _setup_borrowed(db_session)

    base = ResourceBaseService(db_session).compute(sc_a)

    emp = next(x for x in base.employees if x.employee_id == e.id)
    assert {d.date: d.hours for d in emp.days}[date(2026, 1, 5)] == 8.0


def test_summary_shows_borrowed_hours_without_subtracting(db_session):
    _e, sc_a = _setup_borrowed(db_session)

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    assert s.booked_by_other_teams_by_role == {}
    assert s.borrowed_by_other_teams_by_role == {"developer": 6.0}
    assert s.available_by_role["developer"] == s.gross_by_role["developer"]


def test_resource_summary_endpoint_returns_borrowed_hours(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    _e, sc_a = _setup_borrowed(db_session)

    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(f"/api/v1/planning/scenarios/{sc_a.id}/resource-summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200, r.text
    assert r.json()["borrowed_by_other_teams_by_role"] == {"developer": 6.0}
    assert r.json()["booked_by_other_teams_by_role"] == {}
