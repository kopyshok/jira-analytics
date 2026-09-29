"""Личная вовлечённость сотрудника главнее задачи и справочника команды:
раскладка фаз, брони в планах других команд, доля прочих работ, расшифровка."""

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.endpoints import resource_planning as rp_api
from app.database import get_db
from app.main import app
from app.models import (
    EmployeePersonalSetting,
    InvolvementDefault,
    PlanningScenario,
    ProductionCalendarDay,
    ResourcePlan,
    ResourcePlanAssignment,
)
from app.services import cross_team_occupancy as cto
from app.services.plan_common import quarter_bounds
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.normed_factory import _erp
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

D = date.fromisoformat


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _calendar(db, start="2026-01-01", end="2026-04-30"):
    """Производственный календарь: 8 ч в будни."""
    d = D(start)
    while d <= D(end):
        wd = d.weekday() < 5
        db.add(ProductionCalendarDay(date=d, is_workday=wd, kind="workday" if wd else "weekend",
                                     hours=8.0 if wd else 0.0))
        d += timedelta(days=1)
    db.flush()


def _dev_default(db, team, value):
    db.add(InvolvementDefault(team=team, role="dev", effective_year=2026,
                              effective_quarter=1, involvement=value))


def _personal(db, emp, value, year=2026, quarter=1):
    db.add(EmployeePersonalSetting(employee_id=emp.id, effective_year=year,
                                   effective_quarter=quarter, involvement=value))


def _erp_plan(db, personal=None, quarter="Q1"):
    """Разработчик ERP, задача 16 ч разработки с вовлечённостью 70%, справочник 90%.

    ``quarter`` — как хранится у плана («Q1» или «4»); личная запись — с него.
    """
    q = cto.quarter_num(quarter)
    q_start, q_end = quarter_bounds(2026, q)
    _calendar(db, q_start.isoformat(), (q_end + timedelta(days=31)).isoformat())
    dev = make_employee(db, "Пряничников", "ERP", role="dev")
    _dev_default(db, "ERP", 0.9)
    if personal is not None:
        _personal(db, dev, personal, quarter=q)
    sc, plan = make_plan(
        db, "ERP", scenario_status="draft", plan_status="draft", quarter=quarter
    )
    item = add_item(db, sc, "Задача ERP", dev=16)
    item.involvement_dev = 0.7
    db.commit()
    ResourcePlanningService(db).compute_schedule(plan.id)
    [row] = db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan.id, ResourcePlanAssignment.phase == "dev"
        )
    ).scalars().all()
    assert row.employee_id == dev.id
    return plan, row


def _daily(row):
    return sorted(json.loads(row.daily_hours_json).values(), reverse=True)


def test_personal_involvement_wins_over_task_and_team(db_session):
    """Личные 100% при задаче 70% и справочнике 90% — фаза берёт 8 ч в день."""
    _, row = _erp_plan(db_session, personal=1.0)

    assert _daily(row) == [8.0, 8.0]


def test_without_personal_task_value_as_before(db_session):
    """Без личной записи — как раньше: значение задачи, 70% от 8 ч."""
    _, row = _erp_plan(db_session)

    assert [round(h, 2) for h in _daily(row)] == [5.6, 5.6, 4.8]


def test_booking_of_other_team_takes_personal_involvement(db_session):
    """Бронь в плане другой команды у человека с личными 100%: вовлечённость
    брони 100%, остатка дня на прочие работы нет."""
    e = make_employee(db_session, "Пряничников", "A", role="dev")
    _dev_default(db_session, "B", 0.9)
    _personal(db_session, e, 1.0)
    sc, plan = make_plan(db_session, "B")
    item = add_item(db_session, sc, "Работа B", dev=6)
    book(db_session, plan, item, e, {"2026-01-05": 6.0})
    db_session.commit()

    [b] = cto.external_bookings(
        db_session, team="A", year=2026, quarter=1, employee_ids=[e.id],
        start=D("2026-01-01"), end=D("2026-03-31"),
    )

    assert b.involvement == 1.0
    capacity = {e.id: {D("2026-01-05"): 8.0}}
    assert cto.occupied_hours([b], capacity, {e.id: 0.1}) == {e.id: {D("2026-01-05"): 6.0}}


def test_base_other_share_from_personal_involvement(db_session):
    """Доля прочих работ в день без задач — из личной вовлечённости, не из справочника."""
    _dev_default(db_session, "A", 0.9)
    dev = make_employee(db_session, "Пряничников", "A", role="dev")
    join_team(db_session, dev, "B")
    _personal(db_session, dev, 1.0)
    db_session.commit()

    assert cto.base_other_share(db_session, [dev], 2026, 1) == {dev.id: 0.0}


def test_phase_explanation_source_is_employee(client, db_session):
    """Расшифровка фазы: вовлечённость 100%, источник — сотрудник."""
    plan, row = _erp_plan(db_session, personal=1.0)

    r = client.get(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/assignments/{row.id}/explain"
    )

    assert r.status_code == 200, r.text
    calc = r.json()["phase_calc"]
    assert calc["involvement_source"] == "employee"
    assert calc["involvement_pct"] == 100
    assert calc["daily_capacity_hours"] == 8.0


def _explain(client, plan_id, assignment_id):
    r = client.get(
        f"/api/v1/resource-planning/resource-plans/{plan_id}/assignments/{assignment_id}/explain"
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_phase_explanation_zero_involvement_is_not_unset(client, db_session):
    """Вовлечённость задачи 0% — это 0%, а не «не задана»: потолок дня 0 ч,
    как у планировщика."""
    _calendar(db_session)
    dev = make_employee(db_session, "Пряничников", "ERP", role="dev")
    sc, plan = make_plan(db_session, "ERP", scenario_status="draft", plan_status="draft")
    item = add_item(db_session, sc, "Задача ERP", dev=8)
    item.involvement_dev = 0.0
    a = book(db_session, plan, item, dev, {"2026-01-05": 8.0})
    db_session.commit()

    calc = _explain(client, plan.id, a.id)["phase_calc"]

    assert (calc["involvement_pct"], calc["involvement_source"]) == (0, "task")
    assert calc["daily_capacity_hours"] == 0.0


def test_phase_explanation_reads_involvement_once(client, db_session, monkeypatch):
    """Вовлечённость фазы в расшифровке считается один раз — и для потолка
    дня, и для блока расчёта фазы."""
    plan, row = _erp_plan(db_session, personal=1.0)
    calls = []
    original = rp_api._effective_involvement

    def counted(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(rp_api, "_effective_involvement", counted)

    _explain(client, plan.id, row.id)

    assert len(calls) == 1


def test_plan_quarter_without_q_prefix_takes_personal(client, db_session):
    """Квартал плана записан как «4», а не «Q4»: личная вовлечённость всё
    равно действует — в раскладке и в расшифровке."""
    plan, row = _erp_plan(db_session, personal=1.0, quarter="4")

    assert _daily(row) == [8.0, 8.0]
    calc = _explain(client, plan.id, row.id)["phase_calc"]
    assert (calc["involvement_source"], calc["involvement_pct"]) == ("employee", 100)


def test_previous_quarter_tail_takes_personal_of_that_quarter(db_session):
    """Хвост брони опорного плана I кв. во II кв.: вовлечённость — по личной
    записи I кв. (100%), а не II кв. (50%)."""
    e = make_employee(db_session, "Пряничников", "A", role="dev")
    _personal(db_session, e, 1.0, quarter=1)
    _personal(db_session, e, 0.5, quarter=2)
    sc, plan = make_plan(db_session, "B", quarter="Q1")
    item = add_item(db_session, sc, "Работа B", dev=6)
    item.involvement_dev = 0.7
    book(db_session, plan, item, e, {"2026-04-01": 6.0})
    db_session.commit()

    [b] = cto.external_bookings(
        db_session, team="A", year=2026, quarter=2, employee_ids=[e.id],
        start=D("2026-04-01"), end=D("2026-06-30"),
    )

    assert b.involvement == 1.0


@pytest.mark.parametrize("personal, residue", [(None, 2.4), (1.0, 0.0)])
def test_daily_load_task_day_residue_uses_personal(client, db_session, personal, residue):
    """«Загрузка по дням»: в день задачи с вовлечённостью 70% остаток дня
    (30% · 8 ч = 2,4 ч) берут нормированные работы; с личными 100% остатка
    нет — нормированные уходят в дни без задач."""
    _types, _p, s, _item = _erp(db_session)
    _calendar(db_session)
    if personal is not None:
        _personal(db_session, s, personal)
    plan = db_session.execute(
        select(ResourcePlan).where(ResourcePlan.team == "ERP")
    ).scalar_one()
    task = add_item(db_session, db_session.get(PlanningScenario, plan.scenario_id), "Работа ERP", dev=5.6)
    task.involvement_dev = 0.7
    book(db_session, plan, task, s, {"2026-01-05": 5.6})
    db_session.commit()

    r = client.get(f"/api/v1/resource-planning/resource-plans/{plan.id}/gantt")

    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["employee_load"] if x["employee_id"] == s.id)
    day = next(d for d in row["days"] if d["date"] == "2026-01-05")
    assert day["normed_hours"] == residue
    assert row["quarter"]["unplaced_hours"] == 0.0
