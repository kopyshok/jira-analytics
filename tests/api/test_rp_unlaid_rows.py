"""Фаза без единого свободного дня: часы не размещены, раскладка пустая.

Такую фазу никто не должен читать как «часы поровну по дням полосы» (так
читаются только старые строки совсем без раскладки): иначе все её часы
ложатся в день начала — ложная загрузка 200–300% в подвале, ложные
пересечения с другими командами и ложные перегрузки в расшифровках.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import get_db
from app.main import app
from app.models import PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan

BASE = "/api/v1/resource-planning/resource-plans"
DAY = "2026-01-05"


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _weekdays(start: str, end: str, hours: float = 6.0) -> dict:
    out, d = {}, date.fromisoformat(start)
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out[d.isoformat()] = hours
        d += timedelta(days=1)
    return out


@pytest.fixture
def unlaid(db_session):
    """Пряничников из команды A занят планом A каждый будний день окна.
    План B привлёк его с закреплённой датой 05.01 — свободных дней нет,
    12 ч фазы не размещены."""
    e = make_employee(db_session, "Пряничников", "A")
    d = make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=1), e,
         _weekdays("2026-01-01", "2026-04-30"))
    sc_b, plan_b = make_plan(db_session, "B")
    row = book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=12), e,
               {DAY: 6.0, "2026-01-06": 6.0}, pinned_start=True, pinned_employee=True)
    db_session.commit()
    ResourcePlanningService(db_session).compute_schedule(plan_b.id)
    db_session.expire_all()
    return {
        "e": e.id, "d": d.id, "sc_b": sc_b, "plan_a": plan_a.id, "plan_b": plan_b.id,
        "row": row.id,
    }


def _gantt(client, plan_id):
    r = client.get(f"{BASE}/{plan_id}/gantt")
    assert r.status_code == 200, r.text
    return r.json()


def _load(body, emp_id, iso):
    row = next(r for r in body["employee_load"] if r["employee_id"] == emp_id)
    return next(x for x in row["days"] if x["date"] == iso)


def _add_real_row(db_session, t, emp_id):
    """Настоящая фаза плана B в тот же день: 6 ч, раскладка есть."""
    item = add_item(db_session, t["sc_b"], "Соседняя работа B", dev=6)
    a = ResourcePlanAssignment(
        plan_id=t["plan_b"], backlog_item_id=item.id, phase="dev", employee_id=emp_id,
        part_number=1, hours_allocated=6.0,
        start_date=date.fromisoformat(DAY), end_date=date.fromisoformat(DAY),
        daily_hours_json=f'{{"{DAY}": 6.0}}',
    )
    db_session.add(a)
    db_session.commit()
    return a.id


def test_unlaid_row_gives_no_phantom_load(client, db_session, unlaid):
    t = unlaid
    row = db_session.get(ResourcePlanAssignment, t["row"])
    assert row.daily_hours_json == "{}"
    types = set(
        db_session.execute(
            select(PlanConflict.type).where(PlanConflict.plan_id == t["plan_b"])
        ).scalars()
    )
    assert "UNPLACED_HOURS" in types
    assert not any(x.startswith("OVERLOAD_") for x in types)

    body_b = _gantt(client, t["plan_b"])
    # Подвал: план B в этот день человека не занимает (раньше — 200%).
    assert _load(body_b, t["e"], DAY)["pct"] == 0.0
    assert _load(body_b, t["e"], DAY)["ext_pct"] == 100.0
    assert [c for c in body_b["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []
    [a] = [x for x in body_b["assignments"] if x["id"] == t["row"]]
    assert a["daily_hours"] == {}

    # Домашняя команда не видит брони B на 12 ч в день начала.
    body_a = _gantt(client, t["plan_a"])
    assert [b for b in body_a["external_bookings"] if b["team"] == "B"] == []
    assert _load(body_a, t["e"], DAY)["ext_pct"] == 0.0

    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['row']}/explain")
    assert r.status_code == 200, r.text
    summary = r.json()["hours_summary"]
    assert (summary["used"], summary["remaining"]) == (0.0, 12.0)


def test_unlaid_row_next_to_real_work(client, db_session, unlaid):
    """Рядом настоящая фаза в тот же день: пересечение и перегрузка — только у неё."""
    t = unlaid
    real = _add_real_row(db_session, t, t["e"])

    body = _gantt(client, t["plan_b"])
    assert _load(body, t["e"], DAY)["pct"] == 100.0  # 6 ч из 6, без 12 ч фантома
    live = [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"]
    assert [c["assignment_id"] for c in live] == [real]

    c = PlanConflict(
        plan_id=t["plan_b"], type="OVERLOAD_HIGH", severity="critical", status="open",
        employee_id=t["e"], assignment_id=real, window_start=datetime(2026, 1, 5),
        message="перегружен", detection_key=f"OVERLOAD_HIGH:{real}:{DAY}",
    )
    db_session.add(c)
    db_session.commit()
    by_conflict = client.get(f"{BASE}/{t['plan_b']}/conflicts/{c.id}/explain").json()
    assert [x["assignment_id"] for x in by_conflict["contributors"]] == [real]
    assert by_conflict["demand_hours"] == 6.0
    by_phase = client.get(f"{BASE}/{t['plan_b']}/assignments/{real}/explain").json()
    [same] = [x for x in by_phase["conflicts"] if x["id"] == c.id]
    assert same["demand_hours"] == 6.0
    assert [x["assignment_id"] for x in same["contributors"]] == [real]


def test_employee_change_preview_ignores_unlaid_row(client, db_session, unlaid):
    """Передать Пряничникову фазу на 05.01: его не размещённая фаза этот день
    не занимает — перегрузки нет."""
    t = unlaid
    real = _add_real_row(db_session, t, t["d"])

    r = client.post(
        f"{BASE}/{t['plan_b']}/assignments/{real}/preview-employee-change",
        json={"employee_id": t["e"]},
    )

    assert r.status_code == 200, r.text
    assert r.json()["overloads"] == []
