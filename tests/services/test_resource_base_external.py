"""База ресурса сценария вычитает часы, забронированные другими командами."""

from datetime import date

from app.models import EmployeeTeam, Team, TeamSubgroup
from app.services.resource_base_service import ResourceBaseService
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan
from tests.subgroup_fixtures import share


def _setup(db_session, primary="B"):
    """E состоит в A и в B (общий сотрудник, основная — ``primary``); B
    бронирует его на 05.01. Сценарий — команды A."""
    e = make_employee(db_session, "Пряничников", primary)
    join_team(db_session, e, "A" if primary == "B" else "B")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=6)
    book(db_session, plan_b, item_b, e, {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    db_session.commit()
    return e, sc_a


def test_primary_team_base_keeps_hours_booked_by_secondary_team(db_session):
    """A — основная команда E: бронь B базу A не уменьшает, показана справочно."""
    e, sc_a = _setup(db_session, primary="A")

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    assert s.booked_by_other_teams_by_role == {}
    assert s.borrowed_by_other_teams_by_role == {"developer": 6.0}


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
        db_session.add(share(emp.id, "A", sg))
    db_session.commit()

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    gross_x = s.gross_by_subgroup_role["sg-x"]["developer"]
    gross_y = s.gross_by_subgroup_role["sg-y"]["developer"]
    assert s.available_by_subgroup_role["sg-x"]["developer"] == round(gross_x - 6.0, 2)
    assert s.available_by_subgroup_role["sg-y"]["developer"] == gross_y


def test_subgroup_split_50_50_booking_costs_each_group_half(db_session):
    """Сотрудник поделён 50/50 между группами — бронь другой команды режет
    доступное каждой группы поровну."""
    db_session.add(Team(id="t-a2", name="A", has_subgroups=True))
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id="sg-p", team_id="t-a2", name="P", sort_order=1),
        TeamSubgroup(id="sg-q", team_id="t-a2", name="Q", sort_order=2),
    ])
    e, sc_a = _setup(db_session)  # бронь B: 6 ч на 05.01
    db_session.add(share(e.id, "A", "sg-p", 50))
    db_session.add(share(e.id, "A", "sg-q", 50))
    db_session.commit()

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    gross_p = s.gross_by_subgroup_role["sg-p"]["developer"]
    gross_q = s.gross_by_subgroup_role["sg-q"]["developer"]
    assert s.available_by_subgroup_role["sg-p"]["developer"] == round(gross_p - 3.0, 2)
    assert s.available_by_subgroup_role["sg-q"]["developer"] == round(gross_q - 3.0, 2)


def test_subgroup_transfer_after_booking_charges_old_group_only(db_session):
    """Перевод вступает в силу на следующий день после брони — бронь снимается
    только со старой группы, не делится между старой и новой."""
    db_session.add(Team(id="t-a3", name="A", has_subgroups=True))
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id="sg-old", team_id="t-a3", name="Old", sort_order=1),
        TeamSubgroup(id="sg-new", team_id="t-a3", name="New", sort_order=2),
    ])
    e, sc_a = _setup(db_session)  # бронь B: 6 ч на 05.01
    db_session.add(share(e.id, "A", "sg-old"))
    db_session.add(share(e.id, "A", "sg-new", valid_from=date(2026, 1, 6)))
    db_session.commit()

    s = ResourceBaseService(db_session).compute_summary(sc_a)

    gross_old = s.gross_by_subgroup_role["sg-old"]["developer"]
    gross_new = s.gross_by_subgroup_role["sg-new"]["developer"]
    assert s.available_by_subgroup_role["sg-old"]["developer"] == round(gross_old - 6.0, 2)
    assert s.available_by_subgroup_role["sg-new"]["developer"] == gross_new


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
    """Сводка режет бронь так же, как база по дням (гостю правила сценария не режут день)."""
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
    # E — гость A: правило A (50%) к нему не применяется; бронь B снимает 6 ч из 8.
    assert {d.date: d.hours for d in emp.days}[date(2026, 1, 5)] == 2.0
    assert s.booked_by_other_teams_by_role == {"developer": 6.0}
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


def _guest_scenario(db_session, block_rule_pct=None):
    """P: основная ERP (правила 55%), вторая — «Блок». Сценарий «Блока» — P гость.
    В «Блоке» есть свой разработчик Иванов. ``block_rule_pct`` — правило «Блока»
    для разработчиков (орг. вопросы)."""
    from app.models import ScenarioRule
    from tests.services.normed_factory import _rules, _types

    types = _types(db_session)
    p = make_employee(db_session, "Пряничников", "ERP", role="dev")
    make_employee(db_session, "Шутов", "ERP", role="dev")
    join_team(db_session, p, "Блок")
    ivanov = make_employee(db_session, "Иванов", "Блок", role="dev")
    erp_sc, _ = make_plan(db_session, "ERP")
    _rules(db_session, erp_sc, types)
    blk_sc, _ = make_plan(db_session, "Блок", scenario_status="draft")
    if block_rule_pct is not None:
        db_session.add(ScenarioRule(scenario_id=blk_sc.id, role="dev",
                                    work_type_id=types["organizational"].id,
                                    percent_of_norm=block_rule_pct))
    db_session.commit()
    return p, ivanov, erp_sc, blk_sc


QUARTER_NORM = 64 * 8.0  # I кв. 2026 без записей календаря


def test_guest_loses_home_normed_works_except_cross_team_type(db_session):
    p, ivanov, _erp, blk = _guest_scenario(db_session)

    s = ResourceBaseService(db_session).compute_summary(blk)

    home_normed = 0.45 * QUARTER_NORM
    assert round(s.primary_normed_by_role["dev"], 1) == round(home_normed, 1)
    assert round(s.available_by_role["dev"], 1) == round(2 * QUARTER_NORM - home_normed, 1)
    assert [x["display_name"] for x in s.primary_normed_people] == ["Пряничников"]


def test_guest_exempt_from_own_rules_of_secondary_team(db_session):
    """Правило «Блока» 20% режет только своего разработчика, не гостя."""
    p, ivanov, _erp, blk = _guest_scenario(db_session, block_rule_pct=20.0)
    svc = ResourceBaseService(db_session)

    base = {x.employee_id: x.total_hours for x in svc.compute(blk).employees}

    assert round(base[ivanov.id], 1) == round(0.8 * QUARTER_NORM, 1)
    assert round(base[p.id], 1) == round(0.55 * QUARTER_NORM, 1)


def test_guest_daily_base_matches_summary(db_session):
    p, ivanov, _erp, blk = _guest_scenario(db_session, block_rule_pct=20.0)
    svc = ResourceBaseService(db_session)

    total = sum(x.total_hours for x in svc.compute(blk).employees)
    s = svc.compute_summary(blk)

    assert round(total, 1) == round(s.available_by_role["dev"], 1)


def test_home_team_scenario_unchanged(db_session):
    p, _ivanov, erp, _blk = _guest_scenario(db_session)

    s = ResourceBaseService(db_session).compute_summary(erp)

    assert s.primary_normed_by_role == {}
    assert round(s.available_by_role["dev"], 1) == round(2 * 0.45 * QUARTER_NORM, 1)


def test_resource_summary_endpoint_returns_primary_normed(db_session):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.main import app

    _p, _ivanov, _erp, blk = _guest_scenario(db_session)

    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(f"/api/v1/planning/scenarios/{blk.id}/resource-summary")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert r.status_code == 200, r.text
    body = r.json()
    assert round(body["primary_normed_by_role"]["dev"], 1) == round(0.45 * QUARTER_NORM, 1)
    assert [x["display_name"] for x in body["primary_normed_people"]] == ["Пряничников"]
