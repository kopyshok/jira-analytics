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
    assert body["external_bookings"] == []
    row = _row(body, t["e"])
    assert row["is_borrowed"] is False
    assert row["borrowed_from"] is None
    assert _day(row, "2026-01-01")["ext_pct"] == 100.0
    assert _day(row, "2026-01-05")["ext_pct"] == 0.0


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
