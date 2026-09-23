"""Привлечение сотрудников из чужих команд в ресурсный план."""

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import BacklogItem, PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_issue, make_plan

D = date.fromisoformat


def test_borrowed_employee_is_available_outside_plan_team(db_session):
    e = make_employee(db_session, "Чужой", "A")
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    plain = svc.build_availability([e], D("2026-01-05"), D("2026-01-05"), [], team="B")
    borrowed = svc.build_availability(
        [e], D("2026-01-05"), D("2026-01-05"), [], team="B", borrowed={e.id}
    )

    assert plain[e.id][D("2026-01-05")] == 0.0
    assert borrowed[e.id][D("2026-01-05")] == 6.0


def _plain_item(db, title="x", dev=10.0, analyst=0.0, assignee=None, priority=1):
    it = BacklogItem(
        title=title, priority=priority, estimate_dev_hours=dev,
        estimate_analyst_hours=analyst, estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
    )
    db.add(it)
    db.flush()
    return it


def test_jira_developer_from_other_team_wins(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _plain_item(db_session)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], jira_dev={item.id: ext.id}, borrowed={ext.id}
    )

    assert res["dev"][item.id] == ext.id


def test_manual_pin_beats_jira_developer(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _plain_item(db_session)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], pinned={(item.id, "dev", 1): own.id},
        jira_dev={item.id: ext.id}, borrowed={ext.id},
    )

    assert res["dev"][item.id] == own.id


def test_greedy_pool_skips_borrowed(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    a = _plain_item(db_session, "a", priority=2)
    b = _plain_item(db_session, "b", priority=1)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [a, b], [own, ext], borrowed={ext.id}
    )

    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == own.id


def test_analyst_from_other_team_only_manual(db_session):
    b_an = make_employee(db_session, "Аналитик B", "B", role="analyst")
    ext_an = make_employee(db_session, "Аналитик A", "A", role="analyst")
    item = _plain_item(db_session, dev=0.0, analyst=10.0, assignee=ext_an)
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    auto = svc._assign_employees([item], [b_an, ext_an], borrowed={ext_an.id})
    manual = svc._assign_employees(
        [item], [b_an, ext_an], pinned={(item.id, "analyst", 1): ext_an.id},
        borrowed={ext_an.id},
    )

    assert auto["analyst"][item.id] == b_an.id
    assert manual["analyst"][item.id] == ext_an.id


def _dev_rows(db, plan_id):
    return db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == "dev",
        )
    ).scalars().all()


def _days(rows):
    out = set()
    for r in rows:
        out |= {k for k, v in json.loads(r.daily_hours_json or "{}").items() if v > 0}
    return out


def _out_of_team(db, plan_id):
    return db.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan_id, PlanConflict.type == "OUT_OF_TEAM"
        )
    ).scalars().all()


def test_jira_developer_borrowed_and_skips_home_bookings(db_session, sample_project):
    """Техкоманда B берёт разработчика E из A по полю Jira и обходит его брони в A."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    item_a = add_item(db_session, sc_a, "Работа A", dev=12)
    book(db_session, plan_a, item_a, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})

    issue = make_issue(db_session, sample_project, "OS-91393", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = _dev_rows(db_session, plan_b.id)
    assert {r.employee_id for r in rows} == {e.id}
    assert _days(rows) == {"2026-01-05", "2026-01-06"}
    assert _out_of_team(db_session, plan_b.id) == []


def test_home_plan_avoids_borrower_bookings(db_session):
    """Обратная сторона: домашняя команда A обходит часы E в опорном плане B."""
    e = make_employee(db_session, "Пряничников", "A")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=12)
    book(db_session, plan_b, item_b, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    add_item(db_session, sc_a, "Работа A", dev=12)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    rows = _dev_rows(db_session, plan_a.id)
    assert {r.employee_id for r in rows} == {e.id}
    assert _days(rows) == {"2026-01-05", "2026-01-06"}


def test_manual_pin_to_other_team_gets_hours_without_out_of_team(db_session):
    own = make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Чужой", "A")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12)
    db_session.commit()
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan_b.id)

    row = _dev_rows(db_session, plan_b.id)[0]
    assert row.employee_id == own.id
    row.employee_id = ext.id
    row.pinned_employee = True
    db_session.commit()

    svc.compute_schedule(plan_b.id)

    rows = _dev_rows(db_session, plan_b.id)
    assert {r.employee_id for r in rows} == {ext.id}
    assert sum(r.hours_allocated or 0 for r in rows) == 12
    assert _days(rows) == {"2026-01-01", "2026-01-02"}
    assert _out_of_team(db_session, plan_b.id) == []


def test_opo_dev_part_stays_with_borrowed_jira_developer(db_session, sample_project):
    """ОПЭ: часть разработчика — у привлечённого «Разработчика» из Jira."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Свой B", "B")
    an = make_employee(db_session, "Аналитик B", "B", role="analyst")
    issue = make_issue(db_session, sample_project, "OS-1", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=6, issue=issue)
    item.estimate_opo_hours = 4.0
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    opo = db_session.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_b.id,
            ResourcePlanAssignment.phase == "opo",
        )
    ).scalars().all()
    assert {r.employee_id for r in opo} == {an.id, e.id}


def _weekdays(start: str, end: str, hours: float = 6.0) -> dict:
    """{iso: часы} на каждый будний день отрезка."""
    out, d = {}, D(start)
    while d <= D(end):
        if d.weekday() < 5:
            out[d.isoformat()] = hours
        d += timedelta(days=1)
    return out


def _booked_all_window(db, team, employee):
    """Сотрудник занят в опорном плане ``team`` весь квартал и месяц запаса."""
    sc, plan = make_plan(db, team)
    item = add_item(db, sc, f"Работа {team}", dev=1)
    book(db, plan, item, employee, _weekdays("2026-01-01", "2026-04-30"))


def _conflicts(db, plan_id, type_):
    return db.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan_id, PlanConflict.type == type_
        )
    ).scalars().all()


def test_busy_jira_developer_falls_back_to_team_developer(db_session, sample_project):
    """«Разработчик» из Jira занят другой командой весь квартал — берём своего."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    own = make_employee(db_session, "Свой B", "B")
    _booked_all_window(db_session, "A", e)
    issue = make_issue(db_session, sample_project, "OS-2", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = _dev_rows(db_session, plan_b.id)
    assert {r.employee_id for r in rows} == {own.id}
    assert sum(r.hours_allocated or 0 for r in rows) == 12
    assert _conflicts(db_session, plan_b.id, "UNPLACED_HOURS") == []


def test_phase_without_capacity_is_reported_not_dropped(db_session, sample_project):
    """Ни у кого нет ёмкости — разработка не пропадает молча, а даёт конфликт."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    own = make_employee(db_session, "Свой B", "B")
    _booked_all_window(db_session, "A", e)
    _booked_all_window(db_session, "C", own)
    issue = make_issue(db_session, sample_project, "OS-3", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _dev_rows(db_session, plan_b.id) == []
    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.backlog_item_id == item.id
    assert c.severity == "critical"
    assert c.metric_value == 12.0
    assert "Разработка" in c.message
    assert "размещено 0 из 12 ч" in c.message


def test_partially_placed_phase_is_reported(db_session):
    """Часов больше, чем окна у исполнителя: размещённое остаётся, остаток — конфликт."""
    own = make_employee(db_session, "Свой B", "B")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    # Окно — квартал + месяц: 86 будних дней × 6 ч = 516 ч.
    add_item(db_session, sc_b, "Большая", dev=600)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    placed = sum(r.hours_allocated or 0 for r in _dev_rows(db_session, plan_b.id))
    assert placed == 516
    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.employee_id == own.id
    assert c.metric_value == 84.0
    assert "размещено 516 из 600 ч" in c.message
