"""Период основной команды закрывает день человека и в плане другой команды."""

import hashlib
import json
from collections import defaultdict
from datetime import date, datetime

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import MandatoryWorkType, PlanConflict, ResourcePlanAssignment, ScheduledBlock
from app.services import cross_team_occupancy as cto
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, join_team, make_employee, make_plan

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


def _get(db, url):
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        r = TestClient(app).get(url)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200, r.text
    return r.json()


def _guest_in_blok(db):
    """Пряничников: основная ERP (период 12–14.01), в «Блоке» — гость (состоит,
    но не основная). Бронь в плане «Блока» захватывает дни периода ERP."""
    wt = _work_type(db)
    e = make_employee(db, "Пряничников", "ERP", role="dev")
    join_team(db, e, "Блок")
    db.add(ScheduledBlock(team="ERP", start_date=D("2026-01-12"), end_date=D("2026-01-14"),
                          reason="Закрытие месяца", work_type_id=wt.id))
    sc, plan = make_plan(db, "Блок")
    item = add_item(db, sc, "Задача Блока", dev=12)
    a = book(db, plan, item, e, {"2026-01-09": 4.0, "2026-01-13": 4.0, "2026-01-15": 4.0})
    return e, plan, a


def test_conflict_explain_treats_home_block_as_unavailable(db_session):
    """Расшифровка перегрузки гостя в плане другой команды: день периода его
    основной команды — доступно 0 ч, обычный день — полная ёмкость."""
    e, plan, _a = _guest_in_blok(db_session)
    conflicts = {}
    for iso in ("2026-01-13", "2026-01-15"):
        c = PlanConflict(plan_id=plan.id, type="OVERLOAD_HIGH", severity="critical",
                         employee_id=e.id, window_start=datetime.fromisoformat(iso),
                         window_end=datetime.fromisoformat(iso),
                         detection_key=f"OVERLOAD_HIGH:{e.id}:{iso}", message="Перегрузка")
        db_session.add(c)
        conflicts[iso] = c
    db_session.commit()

    base = f"/api/v1/resource-planning/resource-plans/{plan.id}/conflicts"
    blocked = _get(db_session, f"{base}/{conflicts['2026-01-13'].id}/explain")
    free = _get(db_session, f"{base}/{conflicts['2026-01-15'].id}/explain")

    assert blocked["available_hours"] == 0.0
    assert blocked["overload_pct"] is None  # ёмкости нет — процента нет
    assert blocked["demand_hours"] == 4.0
    assert free["available_hours"] > 0.0


def test_assignment_explain_treats_home_block_as_unavailable(db_session):
    """Посуточная расшифровка фазы гостя: дни периода основной команды —
    доступно 0 ч, «Блокировка»; соседние будни доступны."""
    _e, plan, a = _guest_in_blok(db_session)
    db_session.commit()

    body = _get(db_session,
                f"/api/v1/resource-planning/resource-plans/{plan.id}/assignments/{a.id}/explain")

    days = {d["date"]: d for d in body["daily_breakdown"]}
    for iso in ("2026-01-12", "2026-01-14"):
        assert days[iso]["available_hours"] == 0.0
        assert (days[iso]["status"], days[iso]["absence_reason"]) == ("absence", "Блокировка")
    assert days["2026-01-13"]["available_hours"] == 0.0
    for iso in ("2026-01-09", "2026-01-15"):
        assert days[iso]["available_hours"] > 0.0
