"""Диаграмма: нормированные работы по дням, загрузка за квартал, сводка запаса,
живые предупреждения и выбор вида работ у задач других команд."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import get_db
from app.main import app
from app.models import (
    MandatoryWorkType,
    PlanningScenario,
    ProductionCalendarDay,
    ResourcePlan,
    Role,
    ScheduledBlock,
    TeamWorkTypeOverride,
)
from app.services.event_bus import get_event_bus
from tests.services.normed_factory import D, _erp, _rules, _types, _weekdays
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

BASE = "/api/v1/resource-planning"
PLAN_ONLY = {"type": "entity_changed", "entities": ["resource_planning"]}


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


def _calendar(db, start="2026-01-01", end="2026-04-30"):
    """Синхронизированный производственный календарь: 8 ч в будни, как на проде."""
    d = D(start)
    while d <= D(end):
        wd = d.weekday() < 5
        db.add(ProductionCalendarDay(date=d, is_workday=wd, kind="workday" if wd else "weekend",
                                     hours=8.0 if wd else 0.0))
        d += timedelta(days=1)
    db.flush()


def _plan(db, team):
    return db.execute(select(ResourcePlan).where(ResourcePlan.team == team)).scalar_one()


def _gantt(client, plan_id):
    r = client.get(f"{BASE}/resource-plans/{plan_id}/gantt")
    assert r.status_code == 200, r.text
    return r.json()


def _rows(body):
    return {r["employee_id"]: r for r in body["employee_load"]}


def _day(row, iso):
    return next(d for d in row["days"] if d["date"] == iso)


def _erp_with_own_work(db):
    """Пример спеки 5.10: у Пряничникова ещё 176 ч задач ERP (22 полных дня
    вне дней «Блока»)."""
    types, p, s, item = _erp(db)
    _calendar(db)
    db.add(Role(code="dev", label="Разработчик"))
    plan = _plan(db, "ERP")
    sc = db.get(PlanningScenario, plan.scenario_id)
    blok_days = set(_weekdays("2026-01-12", 25))
    own_days = [d for d in _weekdays("2026-01-01", 64) if d not in blok_days][:22]
    book(db, plan, add_item(db, sc, "Работа ERP", dev=176), p, {d: 8.0 for d in own_days})
    db.commit()
    return types, p, s, item, plan


def test_gantt_shows_quarter_load_reserve_and_warnings(client, db_session):
    types, p, s, _item, plan = _erp_with_own_work(db_session)

    body = _gantt(client, plan.id)

    rows = _rows(body)
    q = rows[p.id]["quarter"]
    assert q["capacity_hours"] == 512.0
    assert (q["own_hours"], q["other_teams_hours"], q["normed_hours"]) == (176.0, 180.0, 230.4)
    assert q["unplaced_hours"] == 74.4
    assert q["pct"] == 114.5  # 586,4 / 512
    assert q["pct"] > rows[s.id]["quarter"]["pct"]
    assert {x["label"] for x in q["normed_by_type"]} == {
        "organizational", "support_consult", "minor_change",
    }

    reserve = body["reserve"]
    assert reserve["team"] == "ERP"
    assert [w["label"] for w in reserve["work_types"]] == [
        "organizational", "support_consult", "minor_change", "technical_tasks",
    ]
    dev = next(r for r in reserve["roles"] if r["role"] == "dev")
    assert dev["role_label"] == "Разработчик"
    tech = next(x for x in dev["rows"] if x["label"] == "technical_tasks")
    assert (tech["planned_hours"], tech["other_teams_hours"]) == (102.4, 180.0)
    assert (tech["remaining_hours"], tech["overuse_hours"]) == (0.0, 77.6)
    [work] = reserve["other_team_work"]
    assert (work["team"], work["hours"], work["is_manual"]) == ("Блок", 180.0, False)
    assert work["work_type_id"] == types["technical_tasks"].id

    live = {c["type"]: c for c in body["conflicts"] if c["type"].startswith("NORMED_")}
    overuse = live["NORMED_OVERUSE"]
    assert overuse["id"] == f"live:NORMED_OVERUSE:dev:{types['technical_tasks'].id}"
    assert overuse["message"] == (
        "Разработчик · technical_tasks: заложено 102 ч, другие команды заняли 180 ч"
    )
    assert (overuse["severity"], overuse["is_live"], overuse["metric_value"]) == (
        "warning", True, 77.6,
    )
    unplaced = live["NORMED_UNPLACED"]
    assert unplaced["employee_id"] == p.id
    assert unplaced["message"] == "Пряничников: не вмещается 74 ч нормированных работ"

    # День «Блока»: 7,2 ч другой команды, нормированные — только остаток дня.
    day = _day(rows[p.id], "2026-01-12")
    assert day["ext_pct"] == 90.0 and day["normed_hours"] <= 0.8 + 1e-6
    assert "other_pct" not in day and day["blocked"] is None

    # Живые предупреждения не скрываются — они пересчитываются сами.
    for c in (overuse, unplaced):
        r = client.patch(
            f"{BASE}/resource-plans/{plan.id}/conflicts/{c['id']}", json={"status": "muted"}
        )
        assert r.status_code == 409, r.text


def test_task_day_takes_residue_after_involvement(client, db_session):
    """Вовлечённость «Блока» 90%: в день брони 7,2 ч — 0,8 ч нормированных
    работ, день занят целиком."""
    _types_, p, _s, item = _erp(db_session)
    _calendar(db_session)
    item.involvement_dev = 0.9
    db_session.commit()

    row = _rows(_gantt(client, _plan(db_session, "ERP").id))[p.id]

    day = _day(row, "2026-01-12")
    assert (day["ext_pct"], day["normed_pct"], day["normed_hours"]) == (90.0, 10.0, 0.8)
    free = _day(row, "2026-01-05")
    assert free["pct"] == free["ext_pct"] == 0.0
    assert 0.0 < free["normed_pct"] < 100.0
    assert row["quarter"]["unplaced_hours"] == 0.0


def test_blocked_days_of_primary_team_are_normed_work_in_any_plan(client, db_session):
    """Период основной команды — весь день нормированных работ с подписью, и в
    плане другой команды тоже. Период неосновной команды на показ не влияет,
    даже в тот же день, что период основной, и в плане неосновной команды."""
    types, p, s, _item = _erp(db_session)
    _calendar(db_session)
    # Период «Блока» начинается раньше и попадает на день периода ERP (05.01).
    db_session.add(ScheduledBlock(team="Блок", start_date=D("2026-01-02"), end_date=D("2026-01-05"),
                                  reason="Релиз", work_type_id=types["minor_change"].id))
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца",
                                  work_type_id=types["support_consult"].id))
    db_session.add(ScheduledBlock(team="Блок", start_date=D("2026-01-08"), end_date=D("2026-01-09"),
                                  reason="Релиз", work_type_id=types["minor_change"].id))
    db_session.commit()

    erp = _rows(_gantt(client, _plan(db_session, "ERP").id))
    blok = _rows(_gantt(client, _plan(db_session, "Блок").id))

    for rows in (erp, blok):
        day = _day(rows[p.id], "2026-01-05")
        assert day["blocked"] == "Закрытие месяца · support_consult"
        assert (day["normed_pct"], day["normed_hours"]) == (100.0, 8.0)
        assert _day(rows[p.id], "2026-01-02")["blocked"] is None
        assert _day(rows[p.id], "2026-01-08")["blocked"] is None
    assert _day(erp[s.id], "2026-01-06")["blocked"] == "Закрытие месяца · support_consult"
    support = next(x for x in erp[p.id]["quarter"]["normed_by_type"]
                   if x["label"] == "support_consult")
    assert support["hours"] > 24.0
    # Цифры человека не зависят от плана, в котором на него смотрят: задачи
    # «Блока» в плане ERP — другие команды, в плане «Блока» — свои.
    qe, qb = erp[p.id]["quarter"], blok[p.id]["quarter"]
    assert (qe["own_hours"], qe["other_teams_hours"]) == (0.0, 180.0)
    assert (qb["own_hours"], qb["other_teams_hours"]) == (180.0, 0.0)
    for k in ("capacity_hours", "normed_hours", "unplaced_hours", "pct", "normed_by_type"):
        assert qe[k] == qb[k], k


def test_borrowed_person_quarter_matches_home_plan(client, db_session):
    """Привлечённый в план «Блока» (в «Блоке» не состоит) считается так же, как в
    плане своей основной команды: её периоды закрывают его дни, периоды «Блока» —
    нет."""
    types, _p, s, item = _erp(db_session)
    _calendar(db_session)
    book(db_session, _plan(db_session, "Блок"), item, s,
         {d: 4.0 for d in _weekdays("2026-02-02", 10)})
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-05"), end_date=D("2026-01-07"),
                                  reason="Закрытие месяца",
                                  work_type_id=types["support_consult"].id))
    db_session.add(ScheduledBlock(team="Блок", start_date=D("2026-01-05"), end_date=D("2026-01-09"),
                                  reason="Релиз", work_type_id=types["minor_change"].id))
    db_session.commit()

    home = _rows(_gantt(client, _plan(db_session, "ERP").id))[s.id]
    borrowed = _rows(_gantt(client, _plan(db_session, "Блок").id))[s.id]

    assert borrowed["is_borrowed"] and not home["is_borrowed"]
    for row in (home, borrowed):
        assert _day(row, "2026-01-05")["blocked"] == "Закрытие месяца · support_consult"
        assert _day(row, "2026-01-08")["blocked"] is None
    qh, qb = home["quarter"], borrowed["quarter"]
    assert (qh["own_hours"], qh["other_teams_hours"]) == (0.0, 40.0)
    assert (qb["own_hours"], qb["other_teams_hours"]) == (40.0, 0.0)
    for k in ("capacity_hours", "normed_hours", "unplaced_hours", "pct", "normed_by_type"):
        assert qh[k] == qb[k], k


def test_other_team_plan_has_no_normed_warnings_for_erp_people(client, db_session):
    """У «Блока» свой запас, но перерасход и невмещённые часы людей ERP —
    предупреждения только в планах ERP."""
    types, p, _s, _item, _plan_erp = _erp_with_own_work(db_session)
    bplan = _plan(db_session, "Блок")
    _rules(db_session, db_session.get(PlanningScenario, bplan.scenario_id), types)
    db_session.commit()

    body = _gantt(client, bplan.id)

    assert body["reserve"]["team"] == "Блок"
    assert _rows(body)[p.id]["quarter"]["unplaced_hours"] == 74.4
    assert not [c for c in body["conflicts"] if c["type"].startswith("NORMED_")]


def test_work_type_override(client, db_session):
    types, _p, _s, item = _erp(db_session)
    _calendar(db_session)
    db_session.commit()
    plan_id = _plan(db_session, "ERP").id
    foreign = db_session.execute(
        select(MandatoryWorkType).where(MandatoryWorkType.code == "other_foreign")
    ).scalar_one()
    url = f"{BASE}/work-type-overrides"
    support = types["support_consult"].id

    r = client.put(url, json={"team": "ERP", "backlog_item_id": item.id, "work_type_id": support})

    assert r.status_code == 204, r.text
    client.bus.publish.assert_awaited_once_with(PLAN_ONLY)
    body = _gantt(client, plan_id)
    rows = {x["work_type_id"]: x for x in body["reserve"]["roles"][0]["rows"]}
    assert rows[types["technical_tasks"].id]["other_teams_hours"] == 0.0
    assert rows[support]["other_teams_hours"] == 180.0
    [work] = body["reserve"]["other_team_work"]
    assert (work["work_type_id"], work["is_manual"]) == (support, True)
    # Перерасход переехал в выбранный вид: 180 ч из 153,6 ч сопровождения.
    assert {c["id"] for c in body["conflicts"] if c["type"] == "NORMED_OVERUSE"} == {
        f"live:NORMED_OVERUSE:dev:{support}"
    }

    r = client.put(url, json={"team": "ERP", "backlog_item_id": item.id, "work_type_id": None})
    assert r.status_code == 204, r.text
    [work] = _gantt(client, plan_id)["reserve"]["other_team_work"]
    assert (work["work_type_id"], work["is_manual"]) == (types["technical_tasks"].id, False)

    for wt in ("нет-такого", foreign.id):
        r = client.put(url, json={"team": "ERP", "backlog_item_id": item.id, "work_type_id": wt})
        assert r.status_code == 422, r.text
    r = client.put(url, json={"team": "ERP", "backlog_item_id": "нет-такой", "work_type_id": support})
    assert r.status_code == 404, r.text


def test_work_type_override_requires_team(client, db_session):
    """Без команды выбор не сохраняется; пробелы вокруг названия отбрасываются."""
    types, _p, _s, item = _erp(db_session)
    url = f"{BASE}/work-type-overrides"
    support = types["support_consult"].id

    for team in ("", "   "):
        r = client.put(url, json={"team": team, "backlog_item_id": item.id, "work_type_id": support})
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == "Укажите команду"
    assert db_session.execute(select(TeamWorkTypeOverride)).scalars().all() == []

    r = client.put(url, json={"team": " ERP ", "backlog_item_id": item.id, "work_type_id": support})
    assert r.status_code == 204, r.text
    [row] = db_session.execute(select(TeamWorkTypeOverride)).scalars().all()
    assert (row.team, row.work_type_id) == ("ERP", support)


def test_team_without_rules_has_no_reserve(client, db_session):
    """Нет правил — нет запаса: нормированные работы только в заблокированные дни."""
    types = _types(db_session)
    _calendar(db_session)
    x = make_employee(db_session, "Иванов", "X", role="dev")
    _sc, plan = make_plan(db_session, "X")
    db_session.add(ScheduledBlock(team="X", start_date=D("2026-01-05"), end_date=D("2026-01-06"),
                                  reason="Обучение", work_type_id=types["organizational"].id))
    db_session.commit()

    body = _gantt(client, plan.id)

    assert body["reserve"] is None
    assert not [c for c in body["conflicts"] if c["type"].startswith("NORMED_")]
    row = _rows(body)[x.id]
    assert row["quarter"]["normed_hours"] == 16.0
    assert row["quarter"]["unplaced_hours"] == 0.0
    assert row["quarter"]["normed_by_type"] == [{"label": "organizational", "hours": 16.0}]
    assert _day(row, "2026-01-05")["normed_pct"] == 100.0
    assert _day(row, "2026-01-05")["blocked"] == "Обучение · organizational"
    assert _day(row, "2026-01-07")["normed_hours"] == 0.0


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


def test_gantt_query_count_does_not_grow_with_team_size(client, db_session):
    _types_, _p, _s, item = _erp(db_session)
    _calendar(db_session)
    db_session.commit()
    plan_id = _plan(db_session, "ERP").id
    small = _count_queries(db_session, lambda: _gantt(client, plan_id))

    bplan = _plan(db_session, "Блок")
    for i in range(5):
        e = make_employee(db_session, f"Ещё {i}", "ERP", role="dev")
        join_team(db_session, e, "Блок")
        book(db_session, bplan, item, e, {d: 4.0 for d in _weekdays("2026-02-02", 5)})
    db_session.commit()
    big = _count_queries(db_session, lambda: _gantt(client, plan_id))

    assert big == small
