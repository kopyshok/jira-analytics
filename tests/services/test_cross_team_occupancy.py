"""Занятость сотрудников в опорных планах других команд."""

from datetime import date, datetime

from sqlalchemy import delete, update

from app.models import PlanningScenario, ResourcePlan, ResourcePlanAssignment, ScenarioAllocation
from app.services import cross_team_occupancy as cto
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

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


def test_empty_layout_is_no_booking(db_session):
    """Пустая раскладка — фаза не нашла ни одного свободного дня: человека она
    не занимает. «Поровну по будням» — только у старых строк без раскладки."""
    e, _m = _setup_booked(db_session)
    plan = db_session.query(ResourcePlan).filter_by(team="A").one()
    item = add_item(db_session, db_session.get(PlanningScenario, plan.scenario_id), "Не размещена")
    db_session.add(ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="dev", employee_id=e.id,
        part_number=1, hours_allocated=12.0, daily_hours_json="{}",
        start_date=D("2026-01-13"), end_date=D("2026-01-13"),
    ))
    db_session.commit()

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    )

    assert D("2026-01-13") not in cto.daily_totals(bookings)[e.id]
    assert item.id not in {
        db_session.get(ResourcePlanAssignment, b.assignment_id).backlog_item_id
        for b in bookings
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


def test_quarter_load_pct_counts_all_reference_plans(db_session):
    e, m = _setup_booked(db_session)  # 12 + 9 = 21 ч в опорном плане A

    load = cto.quarter_load_pct(db_session, 2026, 1, [e, m])

    # Q1 2026 без записей календаря: 64 будних дня × 6 ч = 384 ч.
    assert load[e.id] == round(21 / 384 * 100, 1)
    assert load[m.id] == 0.0


def test_previous_quarter_plan_spilling_into_quarter_counts(db_session):
    """План другой команды на прошлый квартал, выползающий в этот, тоже занимает человека."""
    e = make_employee(db_session, "Пряничников", "A")
    sc, plan = make_plan(db_session, "A", year=2025, quarter="Q4")
    item = add_item(db_session, sc, "Хвост Q4", dev=12)
    book(db_session, plan, item, e, {"2025-12-31": 6.0, "2026-01-05": 6.0})
    db_session.commit()

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-04-30"),
    )

    assert cto.daily_totals(bookings) == {e.id: {D("2026-01-05"): 6.0}}
    assert [b.team for b in bookings] == ["A"]
    # Своя команда своим прошлым кварталом не «занимает» — это не чужая бронь.
    assert cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-04-30"),
    ) == []


def test_tail_of_task_carried_into_quarter_plan_counts_once(db_session):
    """Задачу перенесли в план этого квартала — её хвост из прошлого не считается второй раз."""
    e = make_employee(db_session, "Пряничников", "A")
    sc_prev, plan_prev = make_plan(db_session, "A", year=2025, quarter="Q4")
    carried = add_item(db_session, sc_prev, "Переходящая", dev=12)
    book(db_session, plan_prev, carried, e, {"2026-01-05": 6.0, "2026-01-06": 6.0})
    tail = add_item(db_session, sc_prev, "Хвост Q4", dev=6)
    book(db_session, plan_prev, tail, e, {"2026-01-07": 6.0})
    sc_cur, plan_cur = make_plan(db_session, "A")
    db_session.add(ScenarioAllocation(scenario_id=sc_cur.id, backlog_item_id=carried.id))
    book(db_session, plan_cur, carried, e, {"2026-01-05": 6.0, "2026-01-06": 6.0})
    db_session.commit()

    bookings = cto.external_bookings(
        db_session, team=None, year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-04-30"),
    )

    assert cto.daily_totals(bookings) == {
        e.id: {D("2026-01-05"): 6.0, D("2026-01-06"): 6.0, D("2026-01-07"): 6.0}
    }


def test_task_out_of_scenario_no_longer_occupies(db_session):
    """Задачу убрали из сценария или выключили в нём — её фаза, даже закреплённая,
    больше не занимает человека, ещё до пересчёта плана."""
    e = make_employee(db_session, "Пряничников", "A")
    sc, plan = make_plan(db_session, "T", scenario_status="draft")
    removed = add_item(db_session, sc, "Снята «В план»", dev=6)
    book(db_session, plan, removed, e, {"2026-01-05": 6.0},
         pinned_start=True, pinned_employee=True)
    switched_off = add_item(db_session, sc, "Выключена в сценарии", dev=6)
    book(db_session, plan, switched_off, e, {"2026-01-06": 6.0}, pinned_split=True)
    kept = add_item(db_session, sc, "Осталась", dev=6)
    book(db_session, plan, kept, e, {"2026-01-07": 6.0})
    db_session.execute(
        delete(ScenarioAllocation).where(ScenarioAllocation.backlog_item_id == removed.id)
    )
    db_session.execute(
        update(ScenarioAllocation)
        .where(ScenarioAllocation.backlog_item_id == switched_off.id)
        .values(included_flag=False)
    )
    db_session.commit()

    bookings = cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-04-30"),
    )

    assert cto.daily_totals(bookings) == {e.id: {D("2026-01-07"): 6.0}}


def test_tail_counts_again_once_task_left_quarter_scenario(db_session):
    """Перенесённую задачу убрали из сценария квартала: её строка в плане квартала
    не занимает человека, а хвост прошлого квартала снова занимает."""
    e = make_employee(db_session, "Пряничников", "A")
    sc_prev, plan_prev = make_plan(db_session, "A", year=2025, quarter="Q4")
    item = add_item(db_session, sc_prev, "Переходящая", dev=12)
    book(db_session, plan_prev, item, e, {"2026-01-05": 6.0})
    _, plan_cur = make_plan(db_session, "A")  # в сценарии квартала задачи уже нет
    book(db_session, plan_cur, item, e, {"2026-01-12": 6.0}, pinned_start=True)
    db_session.commit()

    bookings = cto.external_bookings(
        db_session, team=None, year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-04-30"),
    )

    assert cto.daily_totals(bookings) == {e.id: {D("2026-01-05"): 6.0}}


def test_external_bookings_tie_broken_by_assignment(db_session):
    """Брони с одинаковыми сотрудником, началом, задачей и фазой — по строке плана."""
    e = make_employee(db_session, "Пряничников", "A")
    sc, plan = make_plan(db_session, "A")
    for row_id in ("ffffffff-0000-0000-0000-000000000000",
                   "00000000-0000-0000-0000-000000000000"):
        item = add_item(db_session, sc, "Без ключа", dev=3)
        book(db_session, plan, item, e, {"2026-01-05": 3.0}, id=row_id)
    db_session.commit()

    bookings = cto.external_bookings(
        db_session, team="B", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    )

    assert [b.assignment_id for b in bookings] == [
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-0000-0000-0000-000000000000",
    ]


def _ext(employee_id, team="B", is_borrowing=False, daily=None, assignment_id=None):
    """Бронь без базы — для чистых функций."""
    daily = daily or {D("2026-01-05"): 6.0}
    return cto.ExternalBooking(
        assignment_id=assignment_id or f"a-{employee_id}-{team}-{is_borrowing}",
        employee_id=employee_id,
        team=team,
        issue_key=None,
        title="x",
        phase="dev",
        start=min(daily),
        end=max(daily),
        daily_hours=daily,
        provisional=False,
        is_borrowing=is_borrowing,
    )


def _booking_of(db_session, employee, team="B", year=2026, quarter="Q1", day="2026-01-05"):
    """Опорный план команды ``team`` с одной бронью на сотрудника."""
    sc, plan = make_plan(db_session, team, year=year, quarter=quarter)
    row = book(db_session, plan, add_item(db_session, sc, f"Работа {team}", dev=6), employee, {day: 6.0})
    return plan, row


def _bookings_for_a(db_session, employee, end="2026-03-31"):
    return cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[employee.id],
        start=D("2026-01-01"), end=D(end),
    )


def test_booking_of_team_without_the_employee_is_borrowing(db_session):
    """Команда B взяла к себе E из A — для A это бронь-привлечение."""
    e = make_employee(db_session, "Шутов", "A")
    _booking_of(db_session, e)
    db_session.commit()

    [b] = _bookings_for_a(db_session, e)

    assert b.is_borrowing is True


def test_booking_of_shared_member_is_not_borrowing(db_session):
    """E состоит и в A, и в B — бронь B на E не привлечение."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    _booking_of(db_session, e)
    db_session.commit()

    [b] = _bookings_for_a(db_session, e)

    assert b.is_borrowing is False


def test_tail_booking_checks_membership_in_its_own_quarter(db_session):
    """Хвост плана B прошлого квартала: тогда E в B состоял — не привлечение,
    хотя в этом квартале он в B уже не состоит."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B", left_at=D("2026-01-01"))
    _booking_of(db_session, e, year=2025, quarter="Q4")
    db_session.commit()

    [b] = _bookings_for_a(db_session, e, end="2026-04-30")

    assert b.is_borrowing is False


def test_subtractable_keeps_borrowing_bookings_only_for_borrowed():
    own_lent = _ext("own", is_borrowing=True)
    own_shared = _ext("own", team="C")
    ext_lent = _ext("ext", is_borrowing=True)

    assert cto.subtractable([own_lent, own_shared, ext_lent], {"ext"}) == [own_shared, ext_lent]


def test_fingerprint_depends_only_on_hours_by_day():
    """Пересчёт чужого плана пересоздаёт строки — отпечаток тот же, пока часы
    человека по дням не изменились; сдвинулись часы — другой отпечаток."""
    one_row = [
        _ext("e", daily={D("2026-01-05"): 6.0, D("2026-01-06"): 6.0}, assignment_id="old")
    ]
    new_rows = [
        _ext("e", daily={D("2026-01-06"): 6.0}, assignment_id="new-2"),
        _ext("e", daily={D("2026-01-05"): 2.0}, assignment_id="new-1"),
        _ext("e", daily={D("2026-01-05"): 4.0}, assignment_id="new-3"),
    ]
    moved = [_ext("e", daily={D("2026-01-05"): 6.0, D("2026-01-07"): 6.0})]

    assert cto.fingerprint(one_row) == cto.fingerprint(new_rows)
    assert cto.fingerprint(one_row) != cto.fingerprint(moved)


def test_stale_teams_compares_fingerprints_by_team():
    was = cto.fingerprint([_ext("e", team="B"), _ext("e", team="C"), _ext("e", team="E")])
    now = [
        _ext("e", team="B", daily={D("2026-01-06"): 6.0}),  # бронь сдвинулась
        _ext("e", team="C"),  # та же
        _ext("e", team="D"),  # новая; E человека освободила
    ]

    assert cto.stale_teams(was, now, datetime(2026, 1, 3)) == ["B", "D", "E"]
    assert cto.stale_teams(cto.fingerprint(now), now, datetime(2026, 1, 3)) == []


def test_stale_teams_without_stored_fingerprint():
    """Посчитан, пока план не запоминал учтённые брони, — устарел, если
    вычитаемые брони есть. Ни разу не считался — не устаревает."""
    bookings = [_ext("e", team="B")]

    assert cto.stale_teams(None, bookings, datetime(2026, 1, 3)) == ["B"]
    assert cto.stale_teams(None, [], datetime(2026, 1, 3)) == []
    assert cto.stale_teams(None, bookings, None) == []
