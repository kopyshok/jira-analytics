"""Закреплённая дата начала: часы раскладываются с неё по свободным окнам."""

import json
from datetime import date, timedelta

from sqlalchemy import select

from app.models import (
    Absence, AbsenceReason, PlanConflict, ProductionCalendarDay, ResourcePlanAssignment,
)
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

D = date.fromisoformat


def _row(db, row_id) -> ResourcePlanAssignment:
    row = db.get(ResourcePlanAssignment, row_id)
    db.refresh(row)
    return row


def _daily(db, row_id) -> dict:
    row = _row(db, row_id)
    return json.loads(row.daily_hours_json) if row.daily_hours_json else {}


def _weekdays(start: str, end: str, hours: float = 6.0) -> dict:
    out, d = {}, D(start)
    while d <= D(end):
        if d.weekday() < 5:
            out[d.isoformat()] = hours
        d += timedelta(days=1)
    return out


def test_pinned_phase_skips_other_team_work(db_session):
    """Шутов состоит в A и B; B занимает его 06.01 — фаза плана A,
    закреплённая с 05.01, этот день обходит."""
    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_b, plan_b = make_plan(db_session, "B")
    book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=6), e,
         {"2026-01-06": 6.0})
    sc_a, plan_a = make_plan(db_session, "A", plan_status="draft")
    item = add_item(db_session, sc_a, "Работа A", dev=12)
    row = book(db_session, plan_a, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_a.id)

    assert _daily(db_session, row.id) == {"2026-01-05": 6.0, "2026-01-07": 6.0}
    fresh = _row(db_session, row.id)
    assert (fresh.start_date, fresh.end_date) == (D("2026-01-05"), D("2026-01-07"))
    assert fresh.pinned_start is True


def test_pinned_phase_of_borrowed_starts_at_first_free_day(db_session):
    """Привлечённый занят домашней командой 05–06.01: закреплённая
    на 05.01 фаза поверх не встаёт и начинается 07.01."""
    e = make_employee(db_session, "Пряничников", "A")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=12), e,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12)
    row = book(db_session, plan_b, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True, pinned_employee=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _daily(db_session, row.id) == {"2026-01-07": 6.0, "2026-01-08": 6.0}
    assert _row(db_session, row.id).start_date == D("2026-01-07")


def test_pinned_phase_skips_holiday_and_absence(db_session):
    e = make_employee(db_session, "Свой", "T")
    db_session.add(ProductionCalendarDay(
        date=D("2026-01-06"), hours=0.0, is_workday=False, kind="holiday", source="manual",
    ))
    reason = AbsenceReason(code="vacation-pin", label="Отпуск", is_planned=True, is_active=True)
    db_session.add(reason)
    db_session.flush()
    db_session.add(Absence(
        employee_id=e.id, start_date=D("2026-01-07"), end_date=D("2026-01-07"),
        reason_id=reason.id,
    ))
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа T", dev=12)
    row = book(db_session, plan, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, row.id) == {"2026-01-05": 6.0, "2026-01-08": 6.0}


def test_pinned_phases_of_one_person_take_turns(db_session):
    """Две закреплённые на 05.01 фазы одного человека: старшая задача
    получает 05.01, младшая — следующий свободный день."""
    e = make_employee(db_session, "Свой", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    first = add_item(db_session, sc, "Первая", dev=6, priority=2)
    second = add_item(db_session, sc, "Вторая", dev=6, priority=1)
    r1 = book(db_session, plan, first, e, {"2026-01-05": 6.0}, pinned_start=True)
    r2 = book(db_session, plan, second, e, {"2026-01-05": 6.0}, pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, r1.id) == {"2026-01-05": 6.0}
    assert _daily(db_session, r2.id) == {"2026-01-06": 6.0}


def test_pinned_testing_phase_follows_its_date(db_session):
    """Тестирование без сотрудника с ручной датой раскладывается по календарю с неё."""
    make_employee(db_session, "Свой", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа T")
    item.estimate_qa_hours = 12.0
    qa = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="qa", employee_id=None,
        part_number=1, hours_allocated=12.0,
        start_date=D("2026-01-12"), end_date=D("2026-01-12"), pinned_start=True,
        daily_hours_json=json.dumps({"2026-01-05": 12.0}),
    )
    db_session.add(qa)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, qa.id) == {"2026-01-12": 6.0, "2026-01-13": 6.0}


def test_pinned_phase_without_free_days_is_reported(db_session):
    """Человек до конца окна занят в команде C, где он тоже состоит, —
    часы закреплённой фазы не размещены, и это видно конфликтом."""
    e = make_employee(db_session, "Свой", "T")
    join_team(db_session, e, "C")
    sc_c, plan_c = make_plan(db_session, "C")
    book(db_session, plan_c, add_item(db_session, sc_c, "Работа C", dev=1), e,
         _weekdays("2026-01-01", "2026-04-30"))
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Работа T", dev=12)
    row = book(db_session, plan, item, e, {"2026-01-05": 6.0, "2026-01-06": 6.0},
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _daily(db_session, row.id) == {}
    [c] = db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all()
    assert c.backlog_item_id == item.id
    assert c.employee_id == e.id
    assert c.metric_value == 12.0
    assert c.message == (
        "Работа T · Разработка 0 из 12 ч — не поместилось в свободные дни исполнителя"
    )


def test_pinned_opo_part_of_analyst_keeps_developer_part(db_session):
    """Закреплена часть ОПЭ аналитика — часть разработчика пересчёт не теряет."""
    an = make_employee(db_session, "Аналитик", "T", role="analyst")
    dev = make_employee(db_session, "Разработчик", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Запуск")
    item.estimate_opo_hours = 8.0
    row = book(db_session, plan, item, an, {"2026-01-12": 4.0}, phase="opo",
               pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    db_session.expire_all()
    parts = {
        r.employee_id: r
        for r in db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan.id,
                ResourcePlanAssignment.phase == "opo",
            )
        ).scalars()
    }
    assert set(parts) == {an.id, dev.id}
    assert parts[an.id].id == row.id
    assert _daily(db_session, row.id) == {"2026-01-12": 4.0}
    assert parts[dev.id].hours_allocated == 4.0
    assert db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all() == []


def test_pinned_testing_phase_without_working_days_is_reported(db_session):
    """Тестирование закреплено на последние выходные окна (квартал и месяц
    запаса) — рабочих дней для его часов нет: часы не размещены, раскладка
    пустая (а не «нет раскладки»), и это видно конфликтом."""
    make_employee(db_session, "Свой", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft", quarter="Q4")
    item = add_item(db_session, sc, "Работа T")
    item.estimate_qa_hours = 12.0
    qa = ResourcePlanAssignment(
        plan_id=plan.id, backlog_item_id=item.id, phase="qa", employee_id=None,
        part_number=1, hours_allocated=12.0,
        start_date=D("2027-01-30"), end_date=D("2027-01-30"), pinned_start=True,
    )
    db_session.add(qa)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _row(db_session, qa.id).daily_hours_json == "{}"
    [c] = db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all()
    assert c.backlog_item_id == item.id
    assert c.metric_value == 12.0
    assert c.message == (
        "Работа T · Тестирование 0 из 12 ч — не поместилось в рабочие дни "
        "с закреплённой даты"
    )


def test_pinned_phase_without_free_days_has_empty_layout(db_session):
    """Не размещённая закреплённая фаза хранит пустую раскладку: читатели не
    раскладывают её часы «поровну по дням полосы» как у старых строк."""
    e = make_employee(db_session, "Свой", "T")
    join_team(db_session, e, "C")
    sc_c, plan_c = make_plan(db_session, "C")
    book(db_session, plan_c, add_item(db_session, sc_c, "Работа C", dev=1), e,
         _weekdays("2026-01-01", "2026-04-30"))
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    row = book(db_session, plan, add_item(db_session, sc, "Работа T", dev=12), e,
               {"2026-01-05": 6.0, "2026-01-06": 6.0}, pinned_start=True)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _row(db_session, row.id).daily_hours_json == "{}"
    # Выравниватель не видит в пустой раскладке перегрузки.
    assert db_session.execute(
        select(PlanConflict.type).where(
            PlanConflict.plan_id == plan.id, PlanConflict.type.like("OVERLOAD_%")
        )
    ).scalars().all() == []


def _opo_rows(db, plan_id) -> dict:
    db.expire_all()
    return {
        r.employee_id: r
        for r in db.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == plan_id,
                ResourcePlanAssignment.phase == "opo",
            )
        ).scalars()
    }


def _team_without_analysts(db_session):
    """В команде нет аналитиков: анализ и часть ОПЭ аналитика ведёт
    исполнитель задачи без роли, часть разработчика — разработчик."""
    x = make_employee(db_session, "Без роли", "T", role=None)
    dev = make_employee(db_session, "Разработчик", "T")
    sc, plan = make_plan(db_session, "T", plan_status="draft")
    item = add_item(db_session, sc, "Запуск", analyst=6, dev=6, assignee=x)
    item.estimate_opo_hours = 8.0
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan.id)
    parts = _opo_rows(db_session, plan.id)
    assert set(parts) == {x.id, dev.id}
    return x, dev, plan, parts


def test_pinned_opo_part_of_no_role_analyst_keeps_developer_part(db_session):
    """Закреплена дата части ОПЭ человека без роли, который ведёт анализ, —
    это часть аналитика: часть разработчика остаётся за разработчиком."""
    x, dev, plan, parts = _team_without_analysts(db_session)
    pinned = parts[x.id]
    pinned.pinned_start = True
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    after = _opo_rows(db_session, plan.id)
    assert set(after) == {x.id, dev.id}
    assert after[x.id].id == pinned.id
    assert after[dev.id].hours_allocated == 4.0


def test_employee_pin_of_no_role_analyst_opo_part_keeps_developer_part(db_session):
    """То же для закрепа исполнителя без даты: часть узнаётся по человеку."""
    x, dev, plan, parts = _team_without_analysts(db_session)
    parts[x.id].pinned_employee = True
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    after = _opo_rows(db_session, plan.id)
    assert set(after) == {x.id, dev.id}
    assert after[x.id].pinned_employee is True
    assert after[dev.id].pinned_employee is False
    assert after[dev.id].hours_allocated == 4.0
