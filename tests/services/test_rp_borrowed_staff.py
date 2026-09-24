"""Привлечение сотрудников из чужих команд в ресурсный план."""

import json
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.models import (
    BacklogItem,
    PlanConflict,
    ResourcePlanAssignment,
    ScenarioAllocation,
)
from app.services import cross_team_occupancy as cto
from app.services.backlog_service import BacklogService
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


def test_busy_jira_developer_does_not_hide_missing_developers(db_session, sample_project):
    """«Разработчик» из Jira не попал в план по ёмкости — «Нет разработчика» остаётся."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Аналитик B", "B", role="analyst")
    _booked_all_window(db_session, "A", e)
    issue = make_issue(db_session, sample_project, "OS-4", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert e.id not in {r.employee_id for r in _dev_rows(db_session, plan_b.id)}
    assert len(_conflicts(db_session, plan_b.id, "NO_DEV")) == 1


def test_borrowed_jira_developer_with_work_covers_missing_developers(
    db_session, sample_project
):
    """Привлечённый разработчик получил разработку — роль в плане закрыта."""
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    make_employee(db_session, "Аналитик B", "B", role="analyst")
    issue = make_issue(db_session, sample_project, "OS-5", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert {r.employee_id for r in _dev_rows(db_session, plan_b.id)} == {e.id}
    assert _conflicts(db_session, plan_b.id, "NO_DEV") == []


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
    assert c.message == (
        "OS-3 Работа B · Разработка 0 из 12 ч — не поместилось в квартал и месяц запаса"
    )


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
    assert c.message == (
        "Большая · Разработка 516 из 600 ч — не поместилось в квартал и месяц запаса"
    )


def test_team_without_analysts_gets_no_unplaced_per_item(db_session):
    """Аналитиков в команде нет — это одна командная запись, а не повтор на каждую задачу."""
    make_employee(db_session, "Свой B", "B")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    for i in range(3):
        add_item(db_session, sc_b, f"Задача {i}", analyst=16, dev=16, priority=10 - i)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert len(_conflicts(db_session, plan_b.id, "NO_ANALYST")) == 1
    assert _conflicts(db_session, plan_b.id, "UNPLACED_HOURS") == []


def test_phase_without_executor_reported_when_team_has_that_role(db_session):
    """Аналитик в плане есть (привлечённый), а у задачи его нет — это видно в конфликте.

    В одной записи — обе причины: анализ без исполнителя, разработка не влезла в окно.
    """
    dev = make_employee(db_session, "Свой B", "B")
    ext_an = make_employee(db_session, "Аналитик A", "A", role="analyst")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    staffed = add_item(db_session, sc_b, "С аналитиком", analyst=12, priority=2)
    orphan = add_item(db_session, sc_b, "Без аналитика", analyst=16, dev=600, priority=1)
    book(db_session, plan_b, staffed, ext_an, {"2026-01-01": 6.0}, phase="analyst",
         pinned_employee=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _conflicts(db_session, plan_b.id, "NO_ANALYST") == []
    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.backlog_item_id == orphan.id
    assert c.employee_id == dev.id
    assert c.metric_value == 100.0
    assert c.message == (
        "Без аналитика · Анализ 0 из 16 ч — нет исполнителя; "
        "Разработка 516 из 600 ч — не поместилось в квартал и месяц запаса"
    )


def test_chain_shortfall_is_one_neutral_conflict_per_initiative(db_session):
    """Анализ упёрся в конец окна, разработка следом не влезла: одна запись на задачу.

    Ёмкость разработчика тут ни при чём — формулировка нейтральная.
    """
    make_employee(db_session, "Аналитик C", "C", role="analyst")
    make_employee(db_session, "Разработчик C", "C")
    sc, plan = make_plan(db_session, "C", plan_status="draft")
    big = add_item(db_session, sc, "Большая", analyst=500, dev=40, priority=10)
    nxt = add_item(db_session, sc, "Следующая", analyst=40, dev=40, priority=5)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    by_item = {c.backlog_item_id: c for c in _conflicts(db_session, plan.id, "UNPLACED_HOURS")}
    assert set(by_item) == {big.id, nxt.id}
    assert by_item[nxt.id].detection_key == f"UNPLACED_HOURS:{nxt.id}"
    assert by_item[nxt.id].metric_value == 64.0
    assert by_item[nxt.id].message == (
        "Следующая · Анализ 16 из 40 ч; Разработка 0 из 40 ч — "
        "не поместилось в квартал и месяц запаса"
    )
    assert by_item[big.id].message == (
        "Большая · Разработка 12 из 40 ч — не поместилось в квартал и месяц запаса"
    )


def test_phase_pushed_by_predecessor_past_free_days_is_reported(db_session):
    """Связь сдвинула фазу туда, где у исполнителя нет ни часа, — это не «размещено»."""
    d1 = make_employee(db_session, "Разработчик 1", "B")
    d2 = make_employee(db_session, "Разработчик 2", "B")
    # Весь апрель (месяц запаса) второй разработчик занят командой C.
    sc_c, plan_c = make_plan(db_session, "C")
    book(db_session, plan_c, add_item(db_session, sc_c, "Работа C", dev=1), d2,
         _weekdays("2026-04-01", "2026-04-30"))
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    long_item = add_item(db_session, sc_b, "Длинная", dev=480, priority=10)
    short_item = add_item(db_session, sc_b, "Короткая", dev=30, priority=5)
    db_session.commit()
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan_b.id)
    rows = {r.backlog_item_id: r for r in _dev_rows(db_session, plan_b.id)}
    for item, emp in ((long_item, d1), (short_item, d2)):
        rows[item.id].employee_id = emp.id
        rows[item.id].pinned_employee = True
    db_session.commit()
    # «Короткая» ждёт «Длинную»: та кончается 22.04, дальше у второго всё занято.
    svc.set_predecessors(rows[short_item.id].id, [rows[long_item.id].id])

    svc.compute_schedule(plan_b.id)

    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.backlog_item_id == short_item.id
    assert c.metric_value == 30.0
    assert c.message == (
        "Короткая · Разработка 0 из 30 ч — не поместилось в квартал и месяц запаса"
    )


def test_unplaced_conflict_disappears_once_hours_fit(db_session):
    """Пересчёт убирает запись, когда часы влезли, — и запись прежнего вида по фазе."""
    make_employee(db_session, "Свой B", "B")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Большая", dev=600)
    db_session.add(PlanConflict(
        plan_id=plan_b.id, type="UNPLACED_HOURS", severity="critical",
        detection_key=f"UNPLACED_HOURS:{item.id}:dev", message="старая запись",
        backlog_item_id=item.id,
    ))
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    svc.compute_schedule(plan_b.id)
    assert [c.detection_key for c in _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")] == [
        f"UNPLACED_HOURS:{item.id}"
    ]

    item.estimate_dev_hours = 12.0
    db_session.commit()
    svc.compute_schedule(plan_b.id)
    assert _conflicts(db_session, plan_b.id, "UNPLACED_HOURS") == []


def _stale_conflict(db, plan):
    db.add(PlanConflict(
        plan_id=plan.id, type="UNPLACED_HOURS", severity="critical",
        detection_key="UNPLACED_HOURS:old", message="старая запись",
    ))


def _all_conflicts(db, plan_id):
    return db.execute(
        select(PlanConflict).where(PlanConflict.plan_id == plan_id)
    ).scalars().all()


def test_plan_without_initiatives_drops_old_conflicts(db_session):
    """Задач в плане не осталось — прежние конфликты при пересчёте уходят."""
    make_employee(db_session, "Свой B", "B")
    _, plan_b = make_plan(db_session, "B", plan_status="draft")
    _stale_conflict(db_session, plan_b)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _all_conflicts(db_session, plan_b.id) == []


def test_plan_without_people_reports_it_instead_of_old_conflicts(db_session):
    """Задачи есть, а людей в команде нет: план пуст, и это видно командными конфликтами."""
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", analyst=8, dev=12)
    _stale_conflict(db_session, plan_b)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert sorted(
        (c.type, c.message) for c in _all_conflicts(db_session, plan_b.id)
    ) == [
        ("NO_ANALYST", "В команде нет аналитиков — расписание фазы анализа невозможно"),
        ("NO_DEV", "В команде нет разработчиков — расписание фазы разработки невозможно"),
    ]


def test_leveler_does_not_delay_onto_other_team_bookings(db_session):
    """Перегрузку выравниватель снимает сдвигом только на дни без чужих броней."""
    e = make_employee(db_session, "Пряничников", "A")
    # План B держит E во вторник 06.01.
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=6)
    book(db_session, plan_b, item_b, e, {"2026-01-06": 6.0})
    # В плане A две разработки E закреплены на понедельник 05.01 — перегрузка.
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    for title, prio in (("Первая", 2), ("Вторая", 1)):
        it = add_item(db_session, sc_a, title, dev=6, priority=prio)
        book(db_session, plan_a, it, e, {"2026-01-05": 6.0}, pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    assert _days(_dev_rows(db_session, plan_a.id)) == {"2026-01-05", "2026-01-07"}


def test_plan_avoids_previous_quarter_spill_of_other_team(db_session):
    """План B на прошлый квартал выполз в январь — план A этот хвост обходит."""
    e = make_employee(db_session, "Пряничников", "A")
    sc_b, plan_b = make_plan(db_session, "B", year=2025, quarter="Q4")
    item_b = add_item(db_session, sc_b, "Хвост B", dev=12)
    book(db_session, plan_b, item_b, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    add_item(db_session, sc_a, "Работа A", dev=12)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    assert _days(_dev_rows(db_session, plan_a.id)) == {"2026-01-05", "2026-01-06"}


def _plan_rows(db, plan_id):
    return db.execute(
        select(ResourcePlanAssignment).where(ResourcePlanAssignment.plan_id == plan_id)
    ).scalars().all()


def test_task_off_plan_frees_borrowed_after_recompute(db_session):
    """Сняли «В план» — пересчёт убирает закреплённую фазу задачи, и привлечённый
    сотрудник больше не занят в плане этой команды."""
    e = make_employee(db_session, "Пряничников", "A")
    make_employee(db_session, "Свой T", "T")
    sc_t, plan_t = make_plan(db_session, "T", scenario_status="draft")
    item = add_item(db_session, sc_t, "Задача T", dev=12)
    book(db_session, plan_t, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
         pinned_start=True, pinned_employee=True)
    db_session.commit()

    item.included_in_planning = False
    db_session.flush()
    BacklogService(db_session)._remove_draft_allocations(item.id)
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan_t.id)

    assert _plan_rows(db_session, plan_t.id) == []
    assert cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-04-30"),
    ) == []


def test_recompute_drops_pinned_phases_only_of_tasks_out_of_scenario(db_session):
    """Закреп задачи, оставшейся в сценарии, пересчёт хранит; закреп ушедшей — убирает."""
    e = make_employee(db_session, "Свой T", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    kept = add_item(db_session, sc, "Осталась", dev=6, priority=2)
    book(db_session, plan, kept, e, {"2026-01-05": 6.0}, pinned_start=True)
    gone = add_item(db_session, sc, "Убрана из сценария", dev=6, priority=1)
    book(db_session, plan, gone, e, {"2026-01-06": 6.0}, pinned_split=True)
    db_session.execute(
        delete(ScenarioAllocation).where(ScenarioAllocation.backlog_item_id == gone.id)
    )
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    rows = _plan_rows(db_session, plan.id)
    assert [(r.backlog_item_id, r.pinned_start) for r in rows] == [(kept.id, True)]


def test_opo_dev_part_shortfall_seen_when_team_has_no_analysts(db_session):
    """Аналитиков нет: часть ОПЭ аналитика покрыта «Нет аналитика», а нехватка
    окна у части разработчика видна; влезшая часть разработчика не спорит."""
    make_employee(db_session, "Свой B", "B")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    fits = add_item(db_session, sc_b, "Запуск", priority=10)
    fits.estimate_opo_hours = 20.0
    big = add_item(db_session, sc_b, "Большой запуск", priority=5)
    big.estimate_opo_hours = 1200.0
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert len(_conflicts(db_session, plan_b.id, "NO_ANALYST")) == 1
    # Окно разработчика — 516 ч, 10 из них ушли на часть «Запуска».
    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.backlog_item_id == big.id
    assert c.metric_value == 94.0
    assert c.message == (
        "Большой запуск · ОПЭ 506 из 600 ч — не поместилось в квартал и месяц запаса"
    )
