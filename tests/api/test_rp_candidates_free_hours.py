"""Карточка фазы: у кандидата — свободные часы в даты фазы и загрузка квартала
с нормированными работами основной команды; внутри группы — по свободным часам."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database import get_db
from app.main import app
from app.models import PlanningScenario, ResourcePlan
from tests.api.test_rp_normed_reserve_gantt import _calendar, _gantt, _rows
from tests.services.normed_factory import _erp, _weekdays
from tests.services.xteam_factory import add_item, book, join_team, make_employee

BASE = "/api/v1/resource-planning/resource-plans"
PHASE_DAYS = _weekdays("2026-01-12", 5)  # 12–16.01: у Пряничникова там «Блок»


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _erp_phase(db):
    """Пример спеки запаса (ERP, разработчики Пряничников и Шутов, «Блок» 180 ч у
    Пряничникова) + фаза плана ERP на 12–16.01 у Пряничникова по 0,8 ч в день."""
    types, p, s, item = _erp(db)
    _calendar(db)
    plan = db.execute(select(ResourcePlan).where(ResourcePlan.team == "ERP")).scalar_one()
    sc = db.get(PlanningScenario, plan.scenario_id)
    row = book(db, plan, add_item(db, sc, "Работа ERP", dev=4), p, {d: 0.8 for d in PHASE_DAYS})
    db.commit()
    return p, s, plan, row


def _candidates(client, plan_id, row_id):
    r = client.get(f"{BASE}/{plan_id}/assignments/{row_id}/candidates")
    assert r.status_code == 200, r.text
    return {g["key"]: g["employees"] for g in r.json()}


def test_candidate_free_hours_in_phase_dates_and_load_with_normed(client, db_session):
    p, s, plan, row = _erp_phase(db_session)

    team = _candidates(client, plan.id, row.id)["team"]

    # Шутов свободнее: идёт первым, хотя по алфавиту второй.
    assert [c["employee_id"] for c in team] == [s.id, p.id]
    by_id = {c["employee_id"]: c for c in team}
    # Шутов: нормированные 230,4 ч ровно по 3,6 ч на каждый из 64 дней —
    # свободно по 4,4 ч в день фазы.
    assert by_id[s.id]["free_hours"] == 22.0
    # Пряничников: «Блок» 7,2 ч в день, нормированные уместились в дни без задач —
    # свободно по 0,8 ч; своя фаза (0,8 ч в день) его не занимает.
    assert by_id[p.id]["free_hours"] == 4.0
    # Загрузка квартала — с нормированными работами, как процент у имени в
    # «Загрузке по дням»; часы самой фазы у нынешнего исполнителя не считаются.
    gantt = _rows(_gantt(client, plan.id))
    assert by_id[s.id]["load_pct"] == gantt[s.id]["quarter"]["pct"] == 45.0
    assert by_id[p.id]["load_pct"] == round((180.0 + 230.4) / 512 * 100, 1)


def test_scenario_row_candidates_keep_tasks_only_load(client, db_session):
    """Кандидаты строки сценария не меняются: без свободных часов, по алфавиту."""
    from app.services.assignee_candidates import candidate_groups
    from app.services.normed_reserve import quarter_bounds

    p, s, _plan, _row = _erp_phase(db_session)
    start, end = quarter_bounds(2026, 1)

    groups = candidate_groups(
        db_session, team="ERP", start=start, end=end, year=2026, quarter=1, jira_employee_id=None,
    )

    team = next(g for g in groups if g.key == "team")
    assert [c.employee_id for c in team.employees] == [p.id, s.id]
    assert all(c.free_hours is None for c in team.employees)


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


def test_candidates_query_count_does_not_grow_with_people(client, db_session):
    _p, _s, plan, row = _erp_phase(db_session)
    small = _count_queries(db_session, lambda: _candidates(client, plan.id, row.id))

    bplan = db_session.execute(select(ResourcePlan).where(ResourcePlan.team == "Блок")).scalar_one()
    bsc = db_session.get(PlanningScenario, bplan.scenario_id)
    item = add_item(db_session, bsc, "Ещё работа", dev=20)
    for i in range(5):
        e = make_employee(db_session, f"Ещё {i}", "ERP", role="dev")
        join_team(db_session, e, "Блок")
        book(db_session, bplan, item, e, {d: 4.0 for d in _weekdays("2026-02-02", 5)})
    db_session.commit()
    big = _count_queries(db_session, lambda: _candidates(client, plan.id, row.id))

    assert big == small
