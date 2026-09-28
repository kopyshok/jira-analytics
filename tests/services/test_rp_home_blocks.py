"""Период основной команды закрывает день человека и в плане другой команды."""

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import MandatoryWorkType, ResourcePlanAssignment, ScheduledBlock
from app.services import cross_team_occupancy as cto
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, join_team, make_employee, make_plan

D = date.fromisoformat


def _work_type(db):
    wt = MandatoryWorkType(code="support_consult", label="Сопровождение", subtracts_from_pool=True)
    db.add(wt)
    db.flush()
    return wt


def test_guest_plan_skips_home_block_days(db_session):
    wt = _work_type(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-12"), end_date=D("2026-01-14"),
                                  reason="Закрытие месяца", work_type_id=wt.id))
    sc, plan = make_plan(db_session, "Блок")
    add_item(db_session, sc, "Задача Блока", dev=80, assignee=e)
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    rows = db_session.query(ResourcePlanAssignment).filter_by(plan_id=plan.id, employee_id=e.id).all()
    days = {D(k) for a in rows for k, v in json.loads(a.daily_hours_json or "{}").items() if v > 0}
    assert days, "фаза должна быть размещена"
    assert not days & {D("2026-01-12"), D("2026-01-13"), D("2026-01-14")}


def test_fingerprint_changes_with_home_block():
    b = []
    assert cto.fingerprint(b) == cto.fingerprint(b, {})
    with_block = cto.fingerprint(b, {"ERP": [("e1", "2026-01-12")]})
    assert with_block != cto.fingerprint(b)
    assert cto.stale_teams(cto.fingerprint(b), b, datetime(2026, 1, 1),
                           {"ERP": [("e1", "2026-01-12")]}) == ["ERP"]


def _old_fingerprint(bookings) -> str:
    """Отпечаток до периодов — как считался раньше (для сверки байт-в-байт)."""
    hours = defaultdict(lambda: defaultdict(float))
    for b in bookings:
        for d, h in b.daily_hours.items():
            hours[b.team][(b.employee_id, d.isoformat())] += h
    out = {}
    for team, cells in hours.items():
        rows = sorted(
            (eid, day, round(h, 2)) for (eid, day), h in cells.items() if round(h, 2) > 0
        )
        if rows:
            raw = json.dumps(rows, separators=(",", ":")).encode("utf-8")
            out[team] = hashlib.sha256(raw).hexdigest()
    return json.dumps(out, sort_keys=True)


def _booking(eid, team, daily):
    return cto.ExternalBooking(
        assignment_id=f"a-{eid}-{team}", employee_id=eid, team=team, issue_key=None,
        title="x", phase="dev", start=min(daily), end=max(daily), daily_hours=daily,
        provisional=False,
    )


def test_fingerprint_without_blocks_is_byte_identical_to_old():
    """Команда без заблокированных дней хэшируется как раньше: запомненные
    отпечатки не устаревают после выпуска."""
    bookings = [
        _booking("e1", "B", {D("2026-01-05"): 6.0, D("2026-01-06"): 2.5}),
        _booking("e2", "B", {D("2026-01-05"): 1.333}),
        _booking("e1", "C", {D("2026-01-07"): 6.0}),
        _booking("e3", "D", {D("2026-01-08"): 0.001}),  # округляется в 0 — не входит
    ]
    old = _old_fingerprint(bookings)

    assert cto.fingerprint(bookings) == old
    assert cto.fingerprint(bookings, {}) == old
    assert cto.fingerprint(bookings, None) == old
    # Периоды другой команды не трогают хэши B и C.
    mixed = json.loads(cto.fingerprint(bookings, {"ERP": [("e1", "2026-01-12")]}))
    assert {k: v for k, v in mixed.items() if k != "ERP"} == json.loads(old)
    assert cto.stale_teams(old, bookings, datetime(2026, 1, 1)) == []
    assert cto.stale_teams(old, bookings, datetime(2026, 1, 1), {}) == []


def _gantt_stale(db, plan_id):
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(f"/api/v1/resource-planning/resource-plans/{plan_id}/gantt")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200, r.text
    return r.json()["stale_teams"]


def test_home_block_change_marks_guest_plan_stale(db_session):
    """Расчёт запоминает периоды основной команды; новый период — план устарел
    с названием основной команды, пересчёт снимает пометку."""
    wt = _work_type(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-12"), end_date=D("2026-01-14"),
                                  reason="Закрытие месяца", work_type_id=wt.id))
    sc, plan = make_plan(db_session, "Блок")
    add_item(db_session, sc, "Задача Блока", dev=80, assignee=e)
    db_session.commit()
    svc = ResourcePlanningService(db_session)
    svc.compute_schedule(plan.id)

    assert _gantt_stale(db_session, plan.id) == []

    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-02-09"), end_date=D("2026-02-10"),
                                  reason="Закрытие месяца", work_type_id=wt.id))
    db_session.commit()
    assert _gantt_stale(db_session, plan.id) == ["ERP"]

    svc.compute_schedule(plan.id)
    assert _gantt_stale(db_session, plan.id) == []


def test_plan_without_items_remembers_home_blocks(db_session):
    """План без задач тоже запоминает периоды основной команды своего состава."""
    wt = _work_type(db_session)
    e = make_employee(db_session, "Пряничников", "ERP", role="dev")
    join_team(db_session, e, "Блок")
    db_session.add(ScheduledBlock(team="ERP", start_date=D("2026-01-12"), end_date=D("2026-01-14"),
                                  reason="Закрытие месяца", work_type_id=wt.id))
    _, plan = make_plan(db_session, "Блок")
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert _gantt_stale(db_session, plan.id) == []
