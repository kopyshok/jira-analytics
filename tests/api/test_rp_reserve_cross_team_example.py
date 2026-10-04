"""Пример пользователя (п.9 комплекта 04.10): часы другой команды расходуют запас
«Технических задач» основной команды человека.

Запас 100 ч, другая команда берёт 80 ч → занято 80, осталось 20, итоговая
загрузка человека за квартал та же, что без брони. Бронь 130 ч → перерасход
30 ч и живое предупреждение плана.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Role, ScenarioRule
from app.services.event_bus import get_event_bus
from tests.api.test_rp_normed_reserve_gantt import _calendar, _gantt, _rows
from tests.services.normed_factory import _types, _weekdays
from tests.services.xteam_factory import add_item, book, make_employee, make_plan

# I кв. 2026: 64 будня × 8 ч = 512 ч; 19,53125% от 512 ч — ровно 100 ч.
TECH_PCT = 19.53125
ORG_PCT = 10.0


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_event_bus] = lambda: AsyncMock()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_event_bus, None)


def _setup(db, booked_days: int):
    """«Склад»: разработчик Иванов, правила разработчика — технические задачи
    100 ч и орг. вопросы 10%. «Техкоманда» бронирует его по 5 ч в день."""
    types = _types(db)
    types["technical_tasks"].label = "Технические задачи"
    _calendar(db)
    db.add(Role(code="dev", label="Разработчик"))
    dev = make_employee(db, "Иванов", "Склад", role="dev")
    sc, plan = make_plan(db, "Склад")
    for code, pct in (("technical_tasks", TECH_PCT), ("organizational", ORG_PCT)):
        db.add(ScenarioRule(scenario_id=sc.id, role="dev", work_type_id=types[code].id,
                            percent_of_norm=pct))
    tsc, tplan = make_plan(db, "Техкоманда")
    if booked_days:
        item = add_item(db, tsc, "Техдолг", dev=5.0 * booked_days)
        book(db, tplan, item, dev, {d: 5.0 for d in _weekdays("2026-01-12", booked_days)})
    db.commit()
    return types, dev, plan, tplan


def _tech_row(body):
    dev = next(r for r in body["reserve"]["roles"] if r["role"] == "dev")
    return next(x for x in dev["rows"] if x["label"] == "Технические задачи")


def _total(quarter):
    return round(quarter["own_hours"] + quarter["other_teams_hours"] + quarter["normed_hours"], 1)


def _quarter_without_booking(client, db):
    _types_, dev, plan, _tplan = _setup(db, 0)
    body = _gantt(client, plan.id)
    tech = _tech_row(body)
    assert (tech["planned_hours"], tech["other_teams_hours"], tech["remaining_hours"]) == (
        100.0, 0.0, 100.0,
    )
    return _rows(body)[dev.id]["quarter"]


@pytest.mark.parametrize(
    "days, other, remaining, overuse",
    [(16, 80.0, 20.0, 0.0), (26, 130.0, 0.0, 30.0)],
)
def test_other_team_hours_eat_tech_reserve(client, db_session, days, other, remaining, overuse):
    _types_, dev, plan, tplan = _setup(db_session, days)

    body = _gantt(client, plan.id)

    tech = _tech_row(body)
    assert tech["planned_hours"] == 100.0
    assert tech["other_teams_hours"] == other
    assert (tech["remaining_hours"], tech["overuse_hours"]) == (remaining, overuse)
    q = _rows(body)[dev.id]["quarter"]
    assert q["capacity_hours"] == 512.0
    assert q["other_teams_hours"] == other
    # Без брони: нормированные 100 (технические) + 51,2 (орг. вопросы) = 151,2 ч.
    # Бронь в пределах запаса итог не меняет; сверх запаса — растёт ровно на перерасход.
    assert _total(q) == round(151.2 + overuse, 1)
    assert q["pct"] == round((151.2 + overuse) / 512 * 100, 1)
    assert q["unplaced_hours"] == 0.0
    warnings = [c for c in body["conflicts"] if c["type"] == "NORMED_OVERUSE"]
    if overuse:
        [w] = warnings
        assert w["metric_value"] == overuse
        assert w["message"] == (
            "Разработчик · Технические задачи: заложено 100 ч, другие команды заняли 130 ч"
        )
    else:
        assert warnings == []
    # Из плана «Техкоманды» человек тот же: её часы — этот план, итог не меняется.
    tq = _rows(_gantt(client, tplan.id))[dev.id]["quarter"]
    assert (tq["own_hours"], tq["other_teams_hours"]) == (other, 0.0)
    assert (_total(tq), tq["pct"]) == (_total(q), q["pct"])


def test_without_booking_reserve_is_whole(client, db_session):
    q = _quarter_without_booking(client, db_session)
    assert (q["other_teams_hours"], q["normed_hours"]) == (0.0, 151.2)
    assert q["pct"] == round(151.2 / 512 * 100, 1)
