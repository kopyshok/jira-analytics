"""Заблокированный период на диаграмме и в расшифровке фазы: штриховка полосы
и причина периода вместо «Отсутствие · Блокировка»."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import ScheduledBlock
from tests.services.xteam_factory import add_item, book, make_employee, make_plan

BASE = "/api/v1/resource-planning/resource-plans"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def blocked_phase(db_session):
    """Разработка 05.01–09.01; 01.01–02.01 (до старта) и 07.01–08.01 закрыты
    периодами команды."""
    e = make_employee(db_session, "Пряничников", "A")
    sc, plan = make_plan(db_session, "A")
    item = add_item(db_session, sc, "Работа A", dev=24)
    row = book(
        db_session, plan, item, e,
        {"2026-01-05": 8.0, "2026-01-06": 8.0, "2026-01-09": 8.0},
    )
    db_session.add(ScheduledBlock(team="A", start_date=date(2026, 1, 1),
                                  end_date=date(2026, 1, 2), reason="Закрытие года"))
    db_session.add(ScheduledBlock(team="A", start_date=date(2026, 1, 7),
                                  end_date=date(2026, 1, 8), reason="Закрытие месяца"))
    db_session.commit()
    return plan, row


def test_gantt_bar_hatches_blocked_days(client, blocked_phase):
    plan, row = blocked_phase
    r = client.get(f"{BASE}/{plan.id}/gantt")
    assert r.status_code == 200, r.text
    a = next(x for x in r.json()["assignments"] if x["id"] == row.id)
    days = {d["date"]: d["type"] for d in a["unavailable_days"]}
    assert days["2026-01-07"] == "block"
    assert days["2026-01-08"] == "block"
    assert "2026-01-06" not in days


def test_explain_shows_block_reason(client, blocked_phase):
    plan, row = blocked_phase
    r = client.get(f"{BASE}/{plan.id}/assignments/{row.id}/explain")
    assert r.status_code == 200, r.text
    body = r.json()
    days = {d["date"]: d for d in body["daily_breakdown"]}
    for iso in ("2026-01-07", "2026-01-08"):
        assert days[iso]["status"] == "blocked"
        assert days[iso]["block_reason"] == "Закрытие месяца"
    assert days["2026-01-01"]["status"] == "blocked"
    assert days["2026-01-01"]["block_reason"] == "Закрытие года"
    assert any("заблокировано (Закрытие года)" in line for line in body["algorithm_log"])
