"""Правки ресурсного плана публикуют entity_changed — другие пользователи видят их сразу.

Где меняются часы людей по дням, событие касается и сценариев: «На бэклог»
других команд вычитает брони опорных планов.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.endpoints.resource_planning import ResourcePlanOut
from app.database import get_db
from app.main import app
from app.models import PlanConflict, ResourcePlan
from app.services.event_bus import get_event_bus
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan

BASE = "/api/v1/resource-planning/resource-plans"
PLAN_ONLY = {"type": "entity_changed", "entities": ["resource_planning"]}
WITH_BOOKINGS = {"type": "entity_changed", "entities": ["resource_planning", "planning"]}


@pytest.fixture
def seeded(testclient_db_session):
    """План команды T: разработка «Задачи» у первого сотрудника, второй свободен."""
    db = testclient_db_session
    dev = make_employee(db, "Свой T", "T")
    other = make_employee(db, "Второй T", "T")
    sc, plan = make_plan(db, "T")
    item = add_item(db, sc, "Задача", dev=12, priority=2)
    second = add_item(db, sc, "Вторая", dev=6, priority=1)
    a = book(db, plan, item, dev, {"2026-01-05": 6.0, "2026-01-06": 6.0})
    db.commit()
    return {"db": db, "plan": plan.id, "item": item.id, "second": second.id,
            "a": a.id, "other": other.id}


def _send(db, method, url, **kw):
    bus = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: bus
    try:
        r = TestClient(app).request(method, url, **kw)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_event_bus, None)
    return r, bus


def test_create_plan(testclient_db_session):
    r, bus = _send(testclient_db_session, "POST", BASE,
                   json={"team": "T", "quarter": "Q1", "year": 2026})
    assert r.status_code == 201, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_compute_plan(seeded):
    r, bus = _send(seeded["db"], "POST", f"{BASE}/{seeded['plan']}/compute")
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_compute_runs_off_event_loop(seeded, monkeypatch):
    """Пересчёт идёт в пуле потоков и не держит запросы других пользователей;
    событие и ответ — прежние: свежий план после пересчёта."""
    db = seeded["db"]
    plan = db.get(ResourcePlan, seeded["plan"])
    plan.status, plan.computed_at = "stale", None
    db.commit()

    where = []
    real = ResourcePlanningService.compute_schedule

    def spy(self, plan_id):
        try:
            asyncio.get_running_loop()
            where.append("event loop")
        except RuntimeError:
            where.append("thread pool")
        return real(self, plan_id)

    monkeypatch.setattr(ResourcePlanningService, "compute_schedule", spy)
    r, bus = _send(db, "POST", f"{BASE}/{seeded['plan']}/compute")
    assert r.status_code == 200, r.text
    assert where == ["thread pool"]
    bus.publish.assert_called_once_with(WITH_BOOKINGS)

    db.expire_all()
    fresh = db.get(ResourcePlan, seeded["plan"])
    assert fresh.status == "ready" and fresh.computed_at is not None
    assert r.json() == ResourcePlanOut.model_validate(fresh).model_dump(mode="json")


def test_missing_plan_publishes_nothing(testclient_db_session):
    r, bus = _send(testclient_db_session, "POST", f"{BASE}/nope/compute")
    assert r.status_code == 404
    bus.publish.assert_not_called()


def test_delete_plan(seeded):
    r, bus = _send(seeded["db"], "DELETE", f"{BASE}/{seeded['plan']}")
    assert r.status_code == 204, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_fork_plan(seeded):
    r, bus = _send(seeded["db"], "POST", f"{BASE}/{seeded['plan']}/fork", json={})
    assert r.status_code == 201, r.text
    bus.publish.assert_called_once_with(PLAN_ONLY)


def test_pin_dates(seeded):
    r, bus = _send(seeded["db"], "PATCH", f"{BASE}/{seeded['plan']}/assignments/{seeded['a']}",
                   json={"start_date": "2026-01-07"})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_change_employee(seeded):
    r, bus = _send(seeded["db"], "PATCH", f"{BASE}/{seeded['plan']}/assignments/{seeded['a']}",
                   json={"employee_id": seeded["other"], "force": True})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_unpin(seeded):
    r, bus = _send(seeded["db"], "DELETE",
                   f"{BASE}/{seeded['plan']}/assignments/{seeded['a']}/manual-edit")
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(PLAN_ONLY)


def test_split_and_merge(seeded):
    url = f"{BASE}/{seeded['plan']}/assignments"
    r, bus = _send(seeded["db"], "POST", f"{url}/{seeded['a']}/split",
                   json={"parts": [6, 6], "cascade": False})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)
    first_part = r.json()["parts"][0]["id"]

    r, bus = _send(seeded["db"], "POST", f"{url}/{first_part}/merge")
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_involvement(seeded):
    r, bus = _send(seeded["db"], "PUT",
                   f"{BASE}/{seeded['plan']}/assignments/{seeded['a']}/involvement",
                   json={"involvement_pct": 50})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_bulk_reset(seeded):
    r, bus = _send(seeded["db"], "POST", f"{BASE}/{seeded['plan']}/bulk-clear",
                   json={"mode": "all"})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(WITH_BOOKINGS)


def test_conflict_status(seeded):
    db = seeded["db"]
    c = PlanConflict(plan_id=seeded["plan"], type="UNPLACED_HOURS", severity="critical",
                     detection_key="UNPLACED_HOURS:x", message="Часы не размещены")
    db.add(c)
    db.commit()
    r, bus = _send(db, "PATCH", f"{BASE}/{seeded['plan']}/conflicts/{c.id}",
                   json={"status": "muted"})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(PLAN_ONLY)


def test_dependencies(seeded):
    db, url = seeded["db"], f"{BASE}/{seeded['plan']}/dependencies"
    r, bus = _send(db, "POST", url,
                   json={"from_item_id": seeded["item"], "to_item_id": seeded["second"]})
    assert r.status_code == 201, r.text
    bus.publish.assert_called_once_with(PLAN_ONLY)
    dep_id = r.json()["id"]

    r, bus = _send(db, "PATCH", f"{url}/{dep_id}", json={"lag_days": 2})
    assert r.status_code == 200, r.text
    bus.publish.assert_called_once_with(PLAN_ONLY)

    r, bus = _send(db, "DELETE", f"{url}/{dep_id}")
    assert r.status_code == 204, r.text
    bus.publish.assert_called_once_with(PLAN_ONLY)
