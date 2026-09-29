"""Диаграмма и выбор исполнителя при привлечении сотрудников из чужих команд."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.project import Project
from tests.services.xteam_factory import add_item, book, make_employee, make_issue, make_plan

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
def two_teams(db_session):
    """E — разработчик команды A; B берёт его на разработку поверх его брони в A."""
    project = Project(jira_project_id="p-x", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-e")
    d = make_employee(db_session, "Свой B", "B")
    other = make_employee(db_session, "Посторонний", "C")

    sc_a, plan_a = make_plan(db_session, "A")
    item_a = add_item(db_session, sc_a, "Работа A", dev=12)
    a_row = book(db_session, plan_a, item_a, e, {"2026-01-01": 6.0, "2026-01-02": 6.0})

    issue = make_issue(db_session, project, "OS-91393", developer="acc-e")
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    b_row = book(
        db_session, plan_b, item_b, e, {"2026-01-01": 6.0, "2026-01-02": 6.0},
        pinned_employee=True,
    )
    db_session.commit()
    return {
        "e": e.id, "d": d.id, "other": other.id,
        "plan_a": plan_a.id, "plan_b": plan_b.id,
        "a_row": a_row.id, "b_row": b_row.id,
    }


def test_candidates_grouped_with_load(client, two_teams):
    t = two_teams
    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/candidates")
    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}

    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [t["e"]]
    assert groups["jira"]["label"] == "Из Jira"
    assert [c["employee_id"] for c in groups["team"]["employees"]] == [t["d"]]
    assert t["other"] in [c["employee_id"] for c in groups["other"]["employees"]]
    jira_e = groups["jira"]["employees"][0]
    assert jira_e["team"] == "A"
    assert 0 < jira_e["load_pct"] < 10  # 24 ч из 384
    assert groups["team"]["employees"][0]["load_pct"] == 0.0


def test_candidates_skip_people_outside_teams_in_quarter(client, db_session, two_teams):
    """Боты и выбывшие до квартала в выбор исполнителя не попадают."""
    from datetime import date

    from app.models.employee_team import EmployeeTeam

    t = two_teams
    bot = make_employee(db_session, "Automation for Jira", None, member=False)
    gone = make_employee(db_session, "Ушедший", "C", member=False)
    db_session.add(EmployeeTeam(employee_id=gone.id, team="C", is_primary=True,
                                left_at=date(2025, 12, 1)))
    db_session.commit()

    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/candidates")
    assert r.status_code == 200, r.text
    ids = {c["employee_id"] for g in r.json() for c in g["employees"]}

    assert ids == {t["e"], t["d"], t["other"]}
    assert bot.id not in ids and gone.id not in ids


def test_candidates_unknown_assignment_is_404(client, two_teams):
    r = client.get(f"{BASE}/{two_teams['plan_b']}/assignments/nope/candidates")
    assert r.status_code == 404


def test_candidates_for_analysis_take_initiative_assignee(client, db_session, two_teams):
    from app.models import BacklogItem, ResourcePlanAssignment

    t = two_teams
    row = db_session.get(ResourcePlanAssignment, t["b_row"])
    row.phase = "analyst"
    db_session.get(BacklogItem, row.backlog_item_id).assignee_employee_id = t["other"]
    db_session.commit()

    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/candidates")
    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}

    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [t["other"]]
    assert t["e"] in [c["employee_id"] for c in groups["other"]["employees"]]


def _gantt(client, plan_id):
    r = client.get(f"{BASE}/{plan_id}/gantt")
    assert r.status_code == 200, r.text
    return r.json()


def _row(body, emp_id):
    return next(r for r in body["employee_load"] if r["employee_id"] == emp_id)


def _day(row, iso):
    return next(d for d in row["days"] if d["date"] == iso)


def test_borrower_plan_shows_overlap_bookings_and_borrowed_row(client, two_teams):
    t = two_teams
    body = _gantt(client, t["plan_b"])

    live = [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"]
    assert len(live) == 1
    assert live[0]["assignment_id"] == t["b_row"]
    assert live[0]["is_live"] is True
    assert live[0]["employee_id"] == t["e"]
    assert "пересекается с планом A" in live[0]["message"]

    assert [(b["employee_id"], b["team"], b["phase"]) for b in body["external_bookings"]] == [
        (t["e"], "A", "dev")
    ]
    assert body["external_bookings"][0]["provisional"] is False
    assert body["external_bookings"][0]["employee_name"] == "Пряничников"
    assert body["external_bookings"][0]["employee_is_borrowed"] is True
    assert body["external_bookings"][0]["is_borrowing"] is False
    assert body["external_bookings"][0]["overlap_days"] == ["2026-01-01", "2026-01-02"]
    assert body["external_bookings"][0]["daily_hours"] == {
        "2026-01-01": 6.0, "2026-01-02": 6.0,
    }

    row = _row(body, t["e"])
    assert row["is_borrowed"] is True
    assert row["borrowed_from"] == "A"
    assert row["left_to"] is None and row["joined_from"] is None
    day = _day(row, "2026-01-01")
    assert day["pct"] == 100.0
    assert day["ext_pct"] == 100.0
    assert day["off"] is None
    assert _day(row, "2026-01-05")["off"] is None  # вне команды B — не «вне команды»
    assert _row(body, t["d"])["is_borrowed"] is False


def test_home_plan_shows_other_team_share_without_conflict(client, two_teams):
    t = two_teams
    body = _gantt(client, t["plan_a"])

    assert [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []
    # Домашней команде видно, куда забрали её человека.
    [b] = body["external_bookings"]
    assert (b["employee_id"], b["team"]) == (t["e"], "B")
    assert b["employee_is_borrowed"] is False
    assert b["is_borrowing"] is True
    # В эти дни и домашний план занял человека — техкоманда получит конфликт.
    assert b["overlap_days"] == ["2026-01-01", "2026-01-02"]
    row = _row(body, t["e"])
    assert row["is_borrowed"] is False
    assert row["borrowed_from"] is None
    assert _day(row, "2026-01-01")["ext_pct"] == 100.0
    assert _day(row, "2026-01-05")["ext_pct"] == 0.0


def test_overlap_marks_only_in_home_reference_plan(client, db_session, two_teams):
    """Отметка «техкоманда получит конфликт» — только в опорном плане
    домашней команды: пересечение у техкоманды считается по нему. В другом
    плане той же команды отметок нет."""
    from app.models import Employee, ResourcePlan, ResourcePlanAssignment

    t = two_teams
    ref = db_session.get(ResourcePlan, t["plan_a"])
    other = ResourcePlan(
        team="A", quarter="Q1", year=2026, status="stale", scenario_id=ref.scenario_id
    )
    db_session.add(other)
    db_session.flush()
    book(
        db_session, other, db_session.get(ResourcePlanAssignment, t["a_row"]).backlog_item,
        db_session.get(Employee, t["e"]), {"2026-01-01": 6.0, "2026-01-02": 6.0},
    )
    db_session.commit()

    [b] = _gantt(client, other.id)["external_bookings"]
    assert (b["team"], b["overlap_days"]) == ("B", [])
    [b_ref] = _gantt(client, t["plan_a"])["external_bookings"]
    assert b_ref["overlap_days"] == ["2026-01-01", "2026-01-02"]


def test_no_live_conflict_when_borrower_fits_next_to_booking(client, db_session, two_teams):
    import json

    from app.models import ResourcePlanAssignment

    t = two_teams
    # В плане B у E по 3 ч в те же дни, в плане A — по 3 ч: вместе 6 ч = ёмкость дня.
    for rid in (t["a_row"], t["b_row"]):
        row = db_session.get(ResourcePlanAssignment, rid)
        row.daily_hours_json = json.dumps({"2026-01-01": 3.0, "2026-01-02": 3.0})
        row.hours_allocated = 6.0
    db_session.commit()

    body = _gantt(client, t["plan_b"])

    assert [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []
    assert body["external_bookings"][0]["overlap_days"] == []
    assert _day(_row(body, t["e"]), "2026-01-01")["ext_pct"] == 50.0


def test_explain_borrowed_assignment_counts_external_bookings(client, two_teams, db_session):
    import json
    from datetime import date

    from app.models import ResourcePlanAssignment

    t = two_teams
    # В плане A оставляем бронь только на 01.01.
    a_row = db_session.get(ResourcePlanAssignment, t["a_row"])
    a_row.daily_hours_json = json.dumps({"2026-01-01": 6.0})
    a_row.end_date = date(2026, 1, 1)
    a_row.hours_allocated = 6.0
    db_session.commit()

    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/explain")
    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["daily_breakdown"]}

    assert days["2026-01-01"]["available_hours"] == 0.0  # занят планом A
    assert days["2026-01-02"]["available_hours"] == 6.0  # свободен, не «вне команды B»


def test_explain_overload_of_borrowed_keeps_raw_capacity(client, two_teams, db_session):
    from datetime import datetime

    from app.models import PlanConflict

    t = two_teams
    c = PlanConflict(
        plan_id=t["plan_b"], type="OVERLOAD_HIGH", severity="critical", status="open",
        employee_id=t["e"], assignment_id=t["b_row"], window_start=datetime(2026, 1, 2),
        message="перегружен", detection_key=f"OVERLOAD_HIGH:{t['b_row']}:2026-01-02",
    )
    db_session.add(c)
    db_session.commit()

    r = client.get(f"{BASE}/{t['plan_b']}/conflicts/{c.id}/explain")
    assert r.status_code == 200, r.text
    # Не «вне команды B» (0 ч) и без вычета брони A — ёмкость дня целиком.
    assert r.json()["available_hours"] == 6.0


LIVE_ID_PREFIX = "live:"


def test_conflict_list_includes_live_overlap(client, two_teams):
    t = two_teams
    gantt_live = [
        c for c in _gantt(client, t["plan_b"])["conflicts"] if c["is_live"]
    ]

    r = client.get(f"{BASE}/{t['plan_b']}/conflicts", params={"group_by": "type"})
    assert r.status_code == 200, r.text
    groups = {g["key"]: g["conflicts"] for g in r.json()["groups"]}
    [live] = groups["CROSS_TEAM_OVERLAP"]
    assert live["is_live"] is True
    assert live["id"] == gantt_live[0]["id"]
    assert live["id"].startswith(LIVE_ID_PREFIX)
    assert live["assignment_id"] == t["b_row"]
    assert live["employee_name"] == "Пряничников"
    assert live["status"] == "open"

    muted = client.get(f"{BASE}/{t['plan_b']}/conflicts", params={"status": "muted"})
    assert muted.json()["groups"] == []


def test_explain_assignment_lists_live_overlap(client, two_teams):
    t = two_teams
    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/explain")
    assert r.status_code == 200, r.text
    [live] = [c for c in r.json()["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"]
    assert live["is_live"] is True
    assert live["date"] == "2026-01-01"
    assert "пересекается с планом A" in live["message"]


def test_explain_live_conflict_returns_base_fields(client, two_teams):
    t = two_teams
    live_id = next(c["id"] for c in _gantt(client, t["plan_b"])["conflicts"] if c["is_live"])

    r = client.get(f"{BASE}/{t['plan_b']}/conflicts/{live_id}/explain")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == live_id
    assert body["type"] == "CROSS_TEAM_OVERLAP"
    assert body["employee_id"] == t["e"]
    assert body["employee_name"] == "Пряничников"
    assert body["date"] == "2026-01-01"
    assert body["contributors"] == []

    gone = client.get(f"{BASE}/{t['plan_b']}/conflicts/live:CROSS_TEAM_OVERLAP:nope/explain")
    assert gone.status_code == 404


def test_live_conflict_status_cannot_change(client, two_teams):
    t = two_teams
    live_id = next(c["id"] for c in _gantt(client, t["plan_b"])["conflicts"] if c["is_live"])

    r = client.patch(f"{BASE}/{t['plan_b']}/conflicts/{live_id}", json={"status": "muted"})

    assert r.status_code == 409
    assert r.json()["detail"] == (
        "Пересечение с планом другой команды нельзя скрыть — оно пересчитывается само"
    )


def test_live_overlap_in_extra_month_after_quarter(client, db_session, two_teams):
    """Окно пересечений — как у броней диаграммы: квартал + месяц запаса."""
    import json
    from datetime import date

    from app.models import ResourcePlanAssignment

    t = two_teams
    for rid in (t["a_row"], t["b_row"]):
        row = db_session.get(ResourcePlanAssignment, rid)
        row.daily_hours_json = json.dumps({"2026-04-01": 6.0, "2026-04-02": 6.0})
        row.start_date, row.end_date = date(2026, 4, 1), date(2026, 4, 2)
    db_session.commit()

    body = _gantt(client, t["plan_b"])

    assert [b["daily_hours"] for b in body["external_bookings"]] == [
        {"2026-04-01": 6.0, "2026-04-02": 6.0}
    ]
    [live] = [c for c in body["conflicts"] if c["is_live"]]
    assert live["assignment_id"] == t["b_row"]
    assert live["window_start"].startswith("2026-04-01")


def test_explain_names_other_team_booking_instead_of_block(client, db_session, two_teams):
    """День, съеденный бронью другой команды, — «занят» её задачей, а не «Блокировка»."""
    import json
    from datetime import date

    from app.models import ResourcePlanAssignment

    t = two_teams
    a_row = db_session.get(ResourcePlanAssignment, t["a_row"])
    proj = db_session.query(Project).filter_by(key="OS").one()
    a_row.backlog_item.issue_id = make_issue(db_session, proj, "OS-7").id
    a_row.daily_hours_json = json.dumps({"2026-01-01": 6.0, "2026-01-05": 2.0})
    a_row.end_date, a_row.hours_allocated = date(2026, 1, 5), 8.0
    b_row = db_session.get(ResourcePlanAssignment, t["b_row"])
    b_row.daily_hours_json = json.dumps({"2026-01-02": 6.0, "2026-01-05": 4.0})
    b_row.start_date, b_row.end_date, b_row.hours_allocated = (
        date(2026, 1, 2), date(2026, 1, 5), 10.0,
    )
    db_session.commit()

    r = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/explain")
    assert r.status_code == 200, r.text
    body = r.json()
    days = {d["date"]: d for d in body["daily_breakdown"]}

    jan1 = days["2026-01-01"]
    assert jan1["is_pre_start"] is True
    assert jan1["status"] == "blocked_by_other"
    assert jan1["blocker_item_key"] == "OS-7"
    assert jan1["blocker_phase_label"] == "Разработка · план A"
    assert jan1["blocker_assignment_id"] is None
    assert days["2026-01-05"]["status"] == "work"
    assert days["2026-01-05"]["co_occupants"] == [
        {"item_key": "OS-7", "phase_label": "Разработка · план A", "hours": 2.0}
    ]
    assert any("занят: OS-7 «Разработка · план A»" in line for line in body["algorithm_log"])


def test_overload_explanations_agree_for_borrowed(client, db_session, two_teams):
    """Расшифровка фазы и расшифровка перегрузки дают одни и те же числа."""
    from datetime import datetime

    from app.models import PlanConflict

    t = two_teams
    c = PlanConflict(
        plan_id=t["plan_b"], type="OVERLOAD_HIGH", severity="critical", status="open",
        employee_id=t["e"], assignment_id=t["b_row"], window_start=datetime(2026, 1, 2),
        message="перегружен", detection_key=f"OVERLOAD_HIGH:{t['b_row']}:2026-01-02",
    )
    db_session.add(c)
    db_session.commit()

    by_conflict = client.get(f"{BASE}/{t['plan_b']}/conflicts/{c.id}/explain").json()
    by_phase = client.get(f"{BASE}/{t['plan_b']}/assignments/{t['b_row']}/explain").json()
    [same] = [x for x in by_phase["conflicts"] if x["id"] == c.id]

    for key in ("available_hours", "demand_hours", "overload_pct"):
        assert same[key] == by_conflict[key], key
    assert same["available_hours"] == 6.0
    # А посуточная таблица показывает, что осталось после брони A.
    days = {d["date"]: d for d in by_phase["daily_breakdown"]}
    assert days["2026-01-02"]["available_hours"] == 0.0


def test_explain_home_employee_ignores_borrowing_booking(client, two_teams):
    """Свой сотрудник: бронь команды, взявшей его к себе, «Доступно» в домашнем
    плане не уменьшает — ровно так его видел планировщик."""
    t = two_teams
    r = client.get(f"{BASE}/{t['plan_a']}/assignments/{t['a_row']}/explain")
    assert r.status_code == 200, r.text
    days = {d["date"]: d for d in r.json()["daily_breakdown"]}

    assert days["2026-01-01"]["available_hours"] == 6.0
    assert days["2026-01-01"]["status"] == "work"


def _compute(db_session, plan_id):
    from app.services.resource_planning_service import ResourcePlanningService

    ResourcePlanningService(db_session).compute_schedule(plan_id)


def _move_booking(db_session, row_id, daily):
    """Сдвинуть бронь: другие дни с часами."""
    import json
    from datetime import date

    from app.models import ResourcePlanAssignment

    row = db_session.get(ResourcePlanAssignment, row_id)
    row.daily_hours_json = json.dumps(daily)
    row.start_date, row.end_date = date.fromisoformat(min(daily)), date.fromisoformat(max(daily))
    row.hours_allocated = sum(daily.values())
    db_session.commit()


def test_plan_computed_before_fingerprints_is_stale_if_bookings_subtracted(
    client, db_session, two_teams
):
    """План B посчитан, когда план ещё не запоминал учтённые брони: какие
    брони A он учёл, неизвестно — считаем устаревшим."""
    from datetime import datetime

    from app.models import ResourcePlan

    t = two_teams
    db_session.get(ResourcePlan, t["plan_b"]).computed_at = datetime(2026, 1, 1)
    db_session.commit()

    body = _gantt(client, t["plan_b"])

    assert body["stale_due_to_other_teams"] is True
    assert body["stale_teams"] == ["A"]


def test_recomputed_plan_is_not_stale(client, db_session, two_teams):
    t = two_teams
    _compute(db_session, t["plan_b"])

    body = _gantt(client, t["plan_b"])

    assert body["stale_due_to_other_teams"] is False
    assert body["stale_teams"] == []


def test_borrower_plan_is_stale_after_home_plan_booking_moved(client, db_session, two_teams):
    """План B посчитан, потом бронь A на Пряничникова сдвинулась."""
    t = two_teams
    _compute(db_session, t["plan_b"])
    _move_booking(db_session, t["a_row"], {"2026-01-02": 6.0, "2026-01-05": 6.0})

    body = _gantt(client, t["plan_b"])

    assert body["stale_due_to_other_teams"] is True
    assert body["stale_teams"] == ["A"]


def test_borrowing_booking_does_not_make_home_plan_stale(client, db_session, two_teams):
    """Бронь техкоманды, взявшей человека к себе, домашний план не занимает —
    и устаревания в нём не даёт: ни у старого расчёта, ни после её сдвига."""
    from datetime import datetime

    from app.models import ResourcePlan

    t = two_teams
    db_session.get(ResourcePlan, t["plan_a"]).computed_at = datetime(2026, 1, 1)
    db_session.commit()

    assert _gantt(client, t["plan_a"])["stale_due_to_other_teams"] is False

    _compute(db_session, t["plan_a"])
    _move_booking(db_session, t["b_row"], {"2026-01-05": 6.0, "2026-01-06": 6.0})

    assert _gantt(client, t["plan_a"])["stale_due_to_other_teams"] is False


@pytest.fixture
def shared_member(db_session):
    """Шутов состоит в A и B; у обеих команд по задаче на 12 ч разработки."""
    from tests.services.xteam_factory import join_team

    s = make_employee(db_session, "Шутов", "A")
    join_team(db_session, s, "B")
    sc_a, plan_a = make_plan(db_session, "A")
    add_item(db_session, sc_a, "Работа A", dev=12)
    sc_b, plan_b = make_plan(db_session, "B")
    add_item(db_session, sc_b, "Работа B", dev=12)
    db_session.commit()
    return {"sc_a": sc_a, "sc_b": sc_b, "plan_a": plan_a.id, "plan_b": plan_b.id}


def test_shared_member_recomputes_do_not_flag_each_other(client, db_session, shared_member):
    """План B вычитает брони основной команды A. Пересчёт пересоздаёт строки, но часы
    человека по дням те же — соседний план не устаревает, и пометки не
    гоняются между командами по кругу."""
    t = shared_member
    for plan_id in (t["plan_a"], t["plan_b"], t["plan_a"]):
        _compute(db_session, plan_id)
    for plan_id in (t["plan_a"], t["plan_b"]):
        assert _gantt(client, plan_id)["stale_due_to_other_teams"] is False, plan_id

    for plan_id in (t["plan_b"], t["plan_a"]):
        _compute(db_session, plan_id)
    for plan_id in (t["plan_a"], t["plan_b"]):
        assert _gantt(client, plan_id)["stale_due_to_other_teams"] is False, plan_id


def test_primary_plan_change_marks_secondary_plan_stale(client, db_session, shared_member):
    """Основная команда A не уступает: её изменение старит план B, а
    изменение B план A не трогает."""
    t = shared_member
    for plan_id in (t["plan_a"], t["plan_b"], t["plan_a"]):
        _compute(db_session, plan_id)
    add_item(db_session, t["sc_a"], "Ещё работа A", dev=6)
    add_item(db_session, t["sc_b"], "Ещё работа B", dev=6)
    db_session.commit()
    _compute(db_session, t["plan_a"])

    body_b = _gantt(client, t["plan_b"])

    assert body_b["stale_due_to_other_teams"] is True
    assert body_b["stale_teams"] == ["A"]

    _compute(db_session, t["plan_b"])

    assert _gantt(client, t["plan_b"])["stale_due_to_other_teams"] is False
    assert _gantt(client, t["plan_a"])["stale_due_to_other_teams"] is False


def test_secondary_plan_gets_overlap_conflict_primary_plan_marks_it(client, db_session):
    """E в A (основная) и в B; оба плана заняли его 01.01–02.01. Конфликт —
    у B, которая уступает; у A — только отметки, что B получит конфликт."""
    from tests.services.xteam_factory import join_team

    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=12), e,
         {"2026-01-01": 6.0, "2026-01-02": 6.0})
    sc_b, plan_b = make_plan(db_session, "B")
    b_row = book(db_session, plan_b, add_item(db_session, sc_b, "Работа B", dev=12), e,
                 {"2026-01-01": 6.0, "2026-01-02": 6.0}, pinned_employee=True)
    db_session.commit()

    body_b = _gantt(client, plan_b.id)
    [live] = [c for c in body_b["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"]
    assert (live["assignment_id"], live["employee_id"]) == (b_row.id, e.id)
    [from_a] = body_b["external_bookings"]
    assert (from_a["team"], from_a["is_borrowing"]) == ("A", False)
    assert from_a["overlap_days"] == ["2026-01-01", "2026-01-02"]

    r = client.get(f"{BASE}/{plan_b.id}/conflicts", params={"group_by": "type"})
    groups = {g["key"]: g["conflicts"] for g in r.json()["groups"]}
    assert [c["id"] for c in groups["CROSS_TEAM_OVERLAP"]] == [live["id"]]

    body_a = _gantt(client, plan_a.id)
    assert [c for c in body_a["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []
    [from_b] = body_a["external_bookings"]
    assert (from_b["team"], from_b["is_borrowing"]) == ("B", True)
    assert from_b["overlap_days"] == ["2026-01-01", "2026-01-02"]


def test_recomputed_plan_without_tasks_is_not_stale(client, db_session):
    """План без задач тоже запоминает брони состава — иначе пометку не
    снимал бы и пересчёт."""
    from tests.services.xteam_factory import join_team

    s = make_employee(db_session, "Шутов", "A")
    join_team(db_session, s, "B")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=12), s,
         {"2026-01-05": 6.0, "2026-01-06": 6.0})
    _, plan_b = make_plan(db_session, "B")
    db_session.commit()

    _compute(db_session, plan_b.id)

    assert _gantt(client, plan_b.id)["stale_due_to_other_teams"] is False


def test_secondary_plan_takes_only_truly_free_hours(client, db_session):
    """Основная команда A заняла Шутова на 90%: 5,4 ч задачи и 0,6 ч
    нормированных работ — день занят целиком. Неосновная B раньше добирала эти
    0,6 ч; теперь её работа встаёт только в свободные дни, а старая раскладка
    поверх нормированных работ — пересечение с планом A."""
    import json

    from app.models import ResourcePlanAssignment
    from tests.services.normed_factory import _rules, _types
    from tests.services.xteam_factory import join_team

    e = make_employee(db_session, "Шутов", "A")
    join_team(db_session, e, "B")
    sc_a, plan_a = make_plan(db_session, "A")
    _rules(db_session, sc_a, _types(db_session), role=None)
    item_a = add_item(db_session, sc_a, "Работа A", dev=10.8)
    item_a.involvement_dev = 0.9
    book(db_session, plan_a, item_a, e, {"2026-01-01": 5.4, "2026-01-02": 5.4})
    sc_b, plan_b = make_plan(db_session, "B")
    item_b = add_item(db_session, sc_b, "Работа B", dev=6)
    book(db_session, plan_b, item_b, e, {"2026-01-01": 0.6, "2026-01-02": 0.6, "2026-01-05": 4.8})
    db_session.commit()

    body = _gantt(client, plan_b.id)
    assert [c["type"] for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == [
        "CROSS_TEAM_OVERLAP"
    ]
    assert body["external_bookings"][0]["overlap_days"] == ["2026-01-01", "2026-01-02"]
    # Домашний план A отмечает те же дни: B получит там конфликт.
    [from_b] = _gantt(client, plan_a.id)["external_bookings"]
    assert from_b["overlap_days"] == ["2026-01-01", "2026-01-02"]

    _compute(db_session, plan_b.id)

    [row] = db_session.query(ResourcePlanAssignment).filter_by(plan_id=plan_b.id).all()
    assert json.loads(row.daily_hours_json) == {"2026-01-05": 6.0}
    body = _gantt(client, plan_b.id)
    assert [c for c in body["conflicts"] if c["type"] == "CROSS_TEAM_OVERLAP"] == []
    day = _day(_row(body, e.id), "2026-01-01")
    assert (day["pct"], day["ext_pct"], day["normed_pct"]) == (0.0, 90.0, 10.0)


def test_load_counts_other_work_share_of_involvement(client, db_session):
    """Загрузка по дням: вовлечённость 90% — 5,4 ч задачи и 0,6 ч
    нормированных работ, день занят целиком. В день, где задача взяла 3 ч, —
    те же 10% дня; остаток запаса ложится сначала на дни без задач и сам
    перегруз не рисует."""
    from tests.services.normed_factory import _rules, _types

    e = make_employee(db_session, "Пряничников", "A")
    sc, plan = make_plan(db_session, "A")
    _rules(db_session, sc, _types(db_session), role=None)
    item = add_item(db_session, sc, "Работа A", dev=8.4)
    item.involvement_dev = 0.9
    book(db_session, plan, item, e, {"2026-01-05": 5.4, "2026-01-06": 3.0})
    db_session.commit()

    row = _row(_gantt(client, plan.id), e.id)

    full = _day(row, "2026-01-05")
    assert (full["pct"], full["normed_pct"], full["normed_hours"]) == (90.0, 10.0, 0.6)
    free = _day(row, "2026-01-07")
    assert free["pct"] == 0.0 and 0.0 < free["normed_pct"] < 100.0
    partial = _day(row, "2026-01-06")
    assert partial["pct"] == 50.0
    # Только 0,6 ч остатка дня по вовлечённости: остаток запаса (55% нормы)
    # целиком помещается в дни без задач, свободные 2,4 ч дня с задачей он
    # берёт лишь при нехватке (спека, раздел 3). Раньше сюда шла ещё и доля
    # запаса пропорционально свободным часам.
    assert partial["normed_hours"] == 0.6
    assert row["quarter"]["unplaced_hours"] == 0.0


def test_secondary_plan_leaves_daily_other_work_on_free_days(client, db_session):
    """В дни, когда основная команда A его не заняла, неосновная B берёт не весь
    день, а по вовлечённости из справочника A (разработчик — 90%). Нормированные
    работы на диаграмме — только из запаса A; у A нет правил, запаса нет, и
    остаток дня слой не заполняет."""
    import json

    from app.models import InvolvementDefault, ResourcePlanAssignment
    from tests.services.xteam_factory import join_team

    db_session.add(InvolvementDefault(
        team="A", role="dev", effective_year=2026, effective_quarter=1, involvement=0.9,
    ))
    e = make_employee(db_session, "Шутов", "A", role="dev")
    join_team(db_session, e, "B")
    make_plan(db_session, "A")
    sc_b, plan_b = make_plan(db_session, "B")
    add_item(db_session, sc_b, "Работа B", dev=10.8)
    db_session.commit()

    _compute(db_session, plan_b.id)

    [row] = db_session.query(ResourcePlanAssignment).filter_by(plan_id=plan_b.id).all()
    assert {k: round(v, 2) for k, v in json.loads(row.daily_hours_json).items()} == {
        "2026-01-01": 5.4, "2026-01-02": 5.4,
    }
    load = _row(_gantt(client, plan_b.id), e.id)
    day = _day(load, "2026-01-01")
    # У A нет правил нормированных работ — запаса нет, слой пуст.
    assert (day["pct"], day["normed_pct"]) == (90.0, 0.0)
    free = _day(load, "2026-01-05")
    assert (free["pct"], free["ext_pct"], free["normed_pct"]) == (0.0, 0.0, 0.0)


def test_jira_developer_left_out_of_plan_does_not_make_it_stale(client, db_session):
    """«Разработчик» из Jira занят весь квартал и в план не попал: его брони
    диаграмма не показывает — и в учтённые при расчёте они не входят."""
    from datetime import date, timedelta

    project = Project(jira_project_id="p-y", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()
    e = make_employee(db_session, "Пряничников", "A", jira_account_id="acc-busy")
    make_employee(db_session, "Свой B", "B")
    sc_a, plan_a = make_plan(db_session, "A")
    busy, d = {}, date(2026, 1, 1)
    while d <= date(2026, 4, 30):
        if d.weekday() < 5:
            busy[d.isoformat()] = 6.0
        d += timedelta(days=1)
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=1), e, busy)
    issue = make_issue(db_session, project, "OS-2", developer="acc-busy")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    add_item(db_session, sc_b, "Работа B", dev=12, issue=issue)
    db_session.commit()

    _compute(db_session, plan_b.id)

    body = _gantt(client, plan_b.id)
    assert e.id not in {a["employee_id"] for a in body["assignments"]}
    assert body["stale_due_to_other_teams"] is False
