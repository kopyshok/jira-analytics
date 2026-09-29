"""Свои проценты нормированных работ сотрудника в базе и сводке сценария."""

from datetime import date

from sqlalchemy import select

from app.models import MandatoryWorkType, PlanningScenario, ScenarioRule, Team, TeamSubgroup
from app.services.resource_base_service import ResourceBaseService
from tests.services.normed_factory import _erp, _personal
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan
from tests.subgroup_fixtures import share

NORM = 64 * 8.0  # I кв. 2026 без записей календаря


def _erp_scenario(db):
    return db.execute(select(PlanningScenario).where(PlanningScenario.team == "ERP")).scalar_one()


def _groups(db, people):
    """Деление ERP на группы: сотрудник → своя группа."""
    db.add(Team(id="t-erp", name="ERP", has_subgroups=True))
    db.flush()
    for i, (emp, sg) in enumerate(people):
        db.add(TeamSubgroup(id=sg, team_id="t-erp", name=sg, sort_order=i))
        db.flush()
        db.add(share(emp.id, "ERP", sg))


def test_spec_example_zero_personal_normed(db_session):
    """Пример спеки 5: у Шутова «свои» 0% — его «На бэклог» — вся норма,
    строки видов работ роли — только часы Пряничникова."""
    types, p, s, _item = _erp(db_session)
    _personal(db_session, s, normed={}, involvement=1.0)
    _groups(db_session, [(p, "sg-p"), (s, "sg-s")])
    db_session.commit()
    sc = _erp_scenario(db_session)
    svc = ResourceBaseService(db_session)

    summary = svc.compute_summary(sc)

    rows = {r.work_type_id: r for r in summary.work_type_rows}
    assert rows[types["technical_tasks"].id].hours_by_role["dev"] == round(0.10 * NORM, 2)
    assert rows[types["minor_change"].id].hours_by_role["dev"] == round(0.20 * NORM, 2)
    # Процент в строке — правило роли, не личный.
    assert rows[types["organizational"].id].pct_by_role["dev"] == 10
    assert summary.gross_by_role["dev"] == 2 * NORM
    # Бронь «Блока» — у Пряничникова, ERP для него основная: не вычитается.
    assert summary.booked_by_other_teams_by_role == {}
    assert summary.available_by_role["dev"] == round(NORM + 0.45 * NORM, 2)
    assert summary.available_by_subgroup_role["sg-s"]["dev"] == NORM
    assert summary.available_by_subgroup_role["sg-p"]["dev"] == round(0.45 * NORM, 2)

    base = svc.compute(sc)

    days = {e.employee_id: {d.hours for d in e.days} for e in base.employees}
    assert days[s.id] == {8.0}
    assert days[p.id] == {3.6}
    assert base.role_totals["dev"] == round(NORM + 0.45 * NORM, 2)


def test_personal_support_only_five_percent(db_session):
    """У Шутова своё — только сопровождение 5%: остальные виды у него 0."""
    types, p, s, _item = _erp(db_session)
    support = types["support_consult"].id
    _personal(db_session, s, normed={support: 5})
    db_session.commit()
    sc = _erp_scenario(db_session)
    svc = ResourceBaseService(db_session)

    summary = svc.compute_summary(sc)

    rows = {r.work_type_id: r for r in summary.work_type_rows}
    assert rows[support].hours_by_role["dev"] == round(0.20 * NORM, 2)
    assert rows[types["organizational"].id].hours_by_role["dev"] == round(0.10 * NORM, 2)
    assert rows[support].pct_by_role["dev"] == 15
    assert summary.available_by_role["dev"] == round(0.95 * NORM + 0.45 * NORM, 2)

    base = svc.compute(sc)

    days = {e.employee_id: {d.hours for d in e.days} for e in base.employees}
    assert days[s.id] == {7.6}


def test_personal_type_missing_in_role_rules_gets_its_own_row(db_session):
    types, p, s, _item = _erp(db_session)
    sc = _erp_scenario(db_session)
    db_session.query(ScenarioRule).filter(
        ScenarioRule.scenario_id == sc.id,
        ScenarioRule.work_type_id == types["minor_change"].id,
    ).delete()
    _personal(db_session, s, normed={types["minor_change"].id: 20})
    db_session.commit()

    summary = ResourceBaseService(db_session).compute_summary(sc)

    row = next(r for r in summary.work_type_rows if r.work_type_id == types["minor_change"].id)
    assert row.hours_by_role["dev"] == round(0.20 * NORM, 2)
    assert row.pct_by_role["dev"] is None


def test_later_quarter_personal_setting_does_not_apply(db_session):
    _types, p, s, _item = _erp(db_session)
    _personal(db_session, s, normed={}, quarter=2)
    db_session.commit()

    base = ResourceBaseService(db_session).compute(_erp_scenario(db_session))

    days = {e.employee_id: {d.hours for d in e.days} for e in base.employees}
    assert days[s.id] == {3.6}


def test_booking_cut_uses_personal_share(db_session):
    """Бронь снимает не больше остатка дня после нормированных работ — по
    личной доле: у сотрудника без нормированных работ остаток — весь день."""
    e = make_employee(db_session, "Пряничников", "B")
    join_team(db_session, e, "A")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=6), e, {"2026-01-05": 6.0})
    sc_a, _ = make_plan(db_session, "A", scenario_status="draft")
    wt = MandatoryWorkType(code="xteam-meet", label="Совещания", subtracts_from_pool=True)
    db_session.add(wt)
    db_session.flush()
    db_session.add(ScenarioRule(
        scenario_id=sc_a.id, role="developer", work_type_id=wt.id, percent_of_norm=50.0,
    ))
    _personal(db_session, e, normed={})
    db_session.commit()
    svc = ResourceBaseService(db_session)

    base = svc.compute(sc_a)
    s = svc.compute_summary(sc_a)

    emp = next(x for x in base.employees if x.employee_id == e.id)
    assert {d.date: d.hours for d in emp.days}[date(2026, 1, 5)] == 2.0
    assert s.booked_by_other_teams_by_role == {"developer": 6.0}
    assert s.available_by_role["developer"] == emp.total_hours
