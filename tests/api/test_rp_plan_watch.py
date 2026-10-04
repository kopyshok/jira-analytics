"""Список наблюдения ресурсного плана: люди любых команд в «Загрузке по дням»
секцией «Наблюдаемые» — те же цифры, что у людей плана, свободно по месяцам и
остаток «Технических задач» основной команды."""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import get_db
from app.main import app
from app.models import PlanningScenario, ResourcePlan, ResourcePlanWatch, Role
from app.services.event_bus import get_event_bus
from tests.api.test_rp_normed_reserve_gantt import _calendar, _gantt, _rows
from tests.services.normed_factory import _erp, _weekdays
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

BASE = "/api/v1/resource-planning/resource-plans"
PLAN_ONLY = {"type": "entity_changed", "entities": ["resource_planning"]}
SAME = ("capacity_hours", "normed_hours", "unplaced_hours", "pct", "normed_by_type",
        "reserve_use")


@pytest.fixture
def client(db_session):
    bus = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    try:
        c = TestClient(app)
        c.bus = bus
        yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_event_bus, None)


def _plan(db, team):
    return db.execute(select(ResourcePlan).where(ResourcePlan.team == team)).scalar_one()


def _setup(db):
    """Пример спеки запаса: ERP (Пряничников — задачи ERP 176 ч и «Блок» 180 ч,
    Шутов — без задач) + техкоманда «Склад» со своим планом и человеком."""
    types, p, s, _item = _erp(db)
    _calendar(db)
    db.add(Role(code="dev", label="Разработчик"))
    erp = _plan(db, "ERP")
    sc = db.get(PlanningScenario, erp.scenario_id)
    blok_days = set(_weekdays("2026-01-12", 25))
    own_days = [d for d in _weekdays("2026-01-01", 64) if d not in blok_days][:22]
    book(db, erp, add_item(db, sc, "Работа ERP", dev=176), p, {d: 8.0 for d in own_days})
    make_employee(db, "Кладовщиков", "Склад", role="dev")
    _sc, sklad = make_plan(db, "Склад")
    db.commit()
    return types, p, s, erp, sklad


def _watch(client, plan_id):
    r = client.get(f"{BASE}/{plan_id}/watch")
    assert r.status_code == 200, r.text
    return r.json()


def _add(client, plan_id, *ids):
    r = client.post(f"{BASE}/{plan_id}/watch", json={"employee_ids": list(ids)})
    assert r.status_code == 204, r.text


def test_watched_person_matches_home_plan_row(client, db_session):
    types, p, s, erp, sklad = _setup(db_session)

    _add(client, sklad.id, p.id, s.id)
    client.bus.publish.assert_awaited_once_with(PLAN_ONLY)
    body = _watch(client, sklad.id)

    # Самые свободные сверху: Шутов свободен, у Пряничникова квартал не вмещается.
    assert [r["employee_id"] for r in body["rows"]] == [s.id, p.id]
    rows = {r["employee_id"]: r for r in body["rows"]}
    home = _rows(_gantt(client, erp.id))
    for eid in (p.id, s.id):
        w, h = rows[eid]["quarter"], home[eid]["quarter"]
        for k in SAME:
            assert w[k] == h[k], (eid, k)
        # Слои — как у человека в плане его команды: свои задачи и другие команды.
        assert (w["own_hours"], w["other_teams_hours"]) == (h["own_hours"], h["other_teams_hours"])
        assert rows[eid]["home_team"] == "ERP"
        assert rows[eid]["in_plan"] is False
        assert not rows[eid]["is_borrowed"]
    assert rows[p.id]["quarter"]["own_hours"] == 176.0
    assert rows[p.id]["quarter"]["other_teams_hours"] == 180.0
    day = next(d for d in rows[p.id]["days"] if d["date"] == "2026-01-12")
    assert (day["pct"], day["ext_pct"]) == (0.0, 90.0)  # «Блок» — другие команды
    day = next(d for d in rows[p.id]["days"] if d["date"] == "2026-01-05")
    assert day["pct"] == 100.0  # задачи ERP — свой слой

    # Свободно: у Шутова нормированные 230,4 ч по 3,6 ч в день — по 4,4 ч свободно.
    assert rows[s.id]["free_hours"] == 281.6
    assert rows[s.id]["free_by_month"] == [
        {"month": "2026-01-01", "hours": 96.8},
        {"month": "2026-02-01", "hours": 88.0},
        {"month": "2026-03-01", "hours": 96.8},
    ]
    assert rows[p.id]["free_hours"] == 0.0
    # Остаток «Технических задач» ERP — общий на роль, как в сводке запаса ERP.
    tech = rows[p.id]["tech_reserve"]
    assert tech == rows[s.id]["tech_reserve"]
    assert (tech["label"], tech["planned_hours"], tech["other_teams_hours"]) == (
        "technical_tasks", 102.4, 180.0,
    )
    assert (tech["remaining_hours"], tech["overuse_hours"]) == (0.0, 77.6)
    # Брони наблюдаемых — для подсказки дня по командам.
    assert {(b["employee_id"], b["team"]) for b in body["bookings"]} == {
        (p.id, "ERP"), (p.id, "Блок"),
    }


def test_watched_in_this_plan_shows_its_hours(client, db_session):
    """Из плана «Блока» Пряничников занят в этом плане: его часы — свой слой
    вместе с задачами ERP; итог квартала тот же."""
    _types, p, _s, erp, sklad = _setup(db_session)
    blok = _plan(db_session, "Блок")
    _add(client, blok.id, p.id)
    _add(client, sklad.id, p.id)

    [w] = _watch(client, blok.id)["rows"]
    [other] = _watch(client, sklad.id)["rows"]

    assert w["in_plan"] is True and other["in_plan"] is False
    assert (w["quarter"]["own_hours"], w["quarter"]["other_teams_hours"]) == (356.0, 0.0)
    for k in SAME:
        assert w["quarter"][k] == other["quarter"][k], k


def test_add_is_idempotent_and_remove(client, db_session):
    _types, p, s, _erp_plan, sklad = _setup(db_session)

    _add(client, sklad.id, p.id)
    _add(client, sklad.id, p.id, s.id)
    assert len(db_session.execute(select(ResourcePlanWatch)).scalars().all()) == 2

    r = client.delete(f"{BASE}/{sklad.id}/watch/{p.id}")
    assert r.status_code == 204, r.text
    assert [x["employee_id"] for x in _watch(client, sklad.id)["rows"]] == [s.id]
    assert client.delete(f"{BASE}/{sklad.id}/watch/{p.id}").status_code == 204
    assert client.bus.publish.await_count == 4

    assert client.post(f"{BASE}/{sklad.id}/watch", json={"employee_ids": ["nope"]}).status_code == 404
    assert client.post(f"{BASE}/nope/watch", json={"employee_ids": [p.id]}).status_code == 404
    assert client.get(f"{BASE}/nope/watch").status_code == 404


def test_inactive_employee_is_rejected(client, db_session):
    _types, p, _s, _erp_plan, sklad = _setup(db_session)
    gone = make_employee(db_session, "Уволенный", "ERP", role="dev", is_active=False)
    db_session.commit()

    r = client.post(f"{BASE}/{sklad.id}/watch", json={"employee_ids": [p.id, gone.id]})

    assert r.status_code == 422, r.text
    assert db_session.execute(select(ResourcePlanWatch)).scalars().all() == []


def test_deleting_employee_clears_his_watch_rows(client, db_session):
    _types, p, s, _erp_plan, sklad = _setup(db_session)
    x = make_employee(db_session, "Временный", "Склад", role="dev")
    db_session.commit()
    _add(client, sklad.id, x.id, s.id)

    db_session.delete(x)
    db_session.commit()

    assert [w.employee_id for w in db_session.execute(select(ResourcePlanWatch)).scalars()] == [s.id]


def test_deleting_plan_clears_its_watch_list(client, db_session):
    _types, p, _s, _erp_plan, sklad = _setup(db_session)
    _add(client, sklad.id, p.id)

    assert client.delete(f"{BASE}/{sklad.id}").status_code == 204

    assert db_session.execute(select(ResourcePlanWatch)).scalars().all() == []


def test_empty_watch_list(client, db_session):
    _types, _p, _s, _erp_plan, sklad = _setup(db_session)
    assert _watch(client, sklad.id) == {"rows": [], "bookings": []}


def _count_queries(db, fn) -> int:
    engine = db.get_bind()
    counter = {"n": 0}

    def _hook(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _hook)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", _hook)
    return counter["n"]


def test_watch_query_count_does_not_grow_with_people(client, db_session):
    _types, p, _s, _erp_plan, sklad = _setup(db_session)
    _add(client, sklad.id, p.id)
    small = _count_queries(db_session, lambda: _watch(client, sklad.id))

    blok = _plan(db_session, "Блок")
    item = add_item(db_session, db_session.get(PlanningScenario, blok.scenario_id), "Ещё", dev=20)
    ids = []
    for i in range(5):
        e = make_employee(db_session, f"Ещё {i}", "ERP", role="dev")
        join_team(db_session, e, "Блок")
        book(db_session, blok, item, e, {d: 4.0 for d in _weekdays("2026-02-02", 5)})
        ids.append(e.id)
    db_session.commit()
    _add(client, sklad.id, *ids)
    big = _count_queries(db_session, lambda: _watch(client, sklad.id))

    assert big == small
