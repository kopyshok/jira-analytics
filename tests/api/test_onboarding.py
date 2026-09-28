"""«Первые шаги»: статус шагов команды, защёлка, ручные отметки, личное состояние."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    Project,
    ResourcePlan,
    TeamOnboardingMark,
)

TEAM = "Команда А"


@pytest.fixture
def client(testclient_db_session):
    def _get_db():
        yield testclient_db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app), testclient_db_session
    finally:
        app.dependency_overrides.pop(get_db, None)


def _status(tc, team=TEAM):
    resp = tc.get("/api/v1/onboarding/status", params={"team": team})
    assert resp.status_code == 200
    return resp.json()


def _project(db):
    p = Project(id="prj-ob", jira_project_id="10001", key="OB", name="OB")
    db.add(p)
    db.commit()
    return p


def _issue(db, n, *, verified=False, category=None, team=TEAM):
    i = Issue(
        id=f"iss-ob-{n}", jira_issue_id=f"20{n:03d}", key=f"OB-{n}", summary=f"Задача {n}",
        issue_type="Task", status="Open",
        project_id="prj-ob", team=team, category_verified=verified, assigned_category=category,
    )
    db.add(i)
    db.commit()
    return i


def test_empty_team_all_pending(client):
    tc, _ = client
    data = _status(tc)
    assert data["team"] == TEAM
    assert set(data["steps"]) == {
        "issues_loaded", "categorization", "team_roles", "absences", "backlog",
        "scenario_created", "scenario_rules", "scenario_involvement", "resource_plan",
    }
    assert all(s["state"] == "pending" for s in data["steps"].values())


def test_no_team_no_steps(client):
    tc, _ = client
    resp = tc.get("/api/v1/onboarding/status")
    assert resp.status_code == 200
    assert resp.json()["steps"] == {}


def test_issues_and_categorization(client):
    tc, db = client
    _project(db)
    for n in range(1, 10):
        _issue(db, n, verified=True, category="support")
    _issue(db, 10)  # одна неразобранная из десяти — ровно порог 10%

    steps = _status(tc)["steps"]
    assert steps["issues_loaded"]["state"] == "done"
    assert steps["issues_loaded"]["source"] == "auto"
    assert steps["categorization"]["state"] == "done"


def test_categorization_above_threshold_pending(client):
    tc, db = client
    _project(db)
    for n in range(1, 9):
        _issue(db, n, verified=True, category="support")
    _issue(db, 9)
    _issue(db, 10)  # 20% неразобранных

    assert _status(tc)["steps"]["categorization"]["state"] == "pending"


def test_latch_survives_data_removal(client):
    tc, db = client
    _project(db)
    _issue(db, 1, verified=True, category="support")
    assert _status(tc)["steps"]["issues_loaded"]["state"] == "done"

    db.query(Issue).delete()
    db.commit()
    assert _status(tc)["steps"]["issues_loaded"]["state"] == "done"


def test_team_roles(client):
    tc, db = client
    db.add_all([
        Employee(id="emp-ob-1", jira_account_id="j-ob-1", display_name="Иванов", is_active=True, role="dev"),
        Employee(id="emp-ob-2", jira_account_id="j-ob-2", display_name="Петров", is_active=True, role=None),
        EmployeeTeam(employee_id="emp-ob-1", team=TEAM, is_primary=True),
        EmployeeTeam(employee_id="emp-ob-2", team=TEAM, is_primary=True),
    ])
    db.commit()
    assert _status(tc)["steps"]["team_roles"]["state"] == "pending"

    db.get(Employee, "emp-ob-2").role = "qa"
    db.commit()
    assert _status(tc)["steps"]["team_roles"]["state"] == "done"


def test_team_roles_ignores_left_and_inactive(client):
    tc, db = client
    db.add_all([
        Employee(id="emp-ob-1", jira_account_id="j-ob-1", display_name="Иванов", is_active=True, role="dev"),
        Employee(id="emp-ob-2", jira_account_id="j-ob-2", display_name="Выбыл", is_active=True, role=None),
        Employee(id="emp-ob-3", jira_account_id="j-ob-3", display_name="Выключен", is_active=False, role=None),
        EmployeeTeam(employee_id="emp-ob-1", team=TEAM, is_primary=True),
        EmployeeTeam(employee_id="emp-ob-2", team=TEAM, is_primary=True, left_at=date(2020, 1, 1)),
        EmployeeTeam(employee_id="emp-ob-3", team=TEAM, is_primary=True),
    ])
    db.commit()
    assert _status(tc)["steps"]["team_roles"]["state"] == "done"


def test_backlog_needs_estimate(client):
    tc, db = client
    db.add(BacklogItem(id="bl-ob-1", title="Идея", team=TEAM))
    db.commit()
    assert _status(tc)["steps"]["backlog"]["state"] == "pending"

    db.get(BacklogItem, "bl-ob-1").estimate_dev_hours = 40
    db.commit()
    assert _status(tc)["steps"]["backlog"]["state"] == "done"


def test_backlog_archived_not_counted(client):
    tc, db = client
    db.add(BacklogItem(id="bl-ob-1", title="Идея", team=TEAM, estimate_dev_hours=40,
                       archived_at=datetime(2026, 1, 1)))
    db.commit()
    assert _status(tc)["steps"]["backlog"]["state"] == "pending"


def test_scenario_and_resource_plan(client):
    tc, db = client
    db.add(PlanningScenario(id="sc-ob-1", name="2026 Q4", team=TEAM, quarter="Q4", year=2026))
    db.add(ResourcePlan(id="rp-ob-1", team=TEAM, quarter="Q4", year=2026))
    db.commit()
    steps = _status(tc)["steps"]
    assert steps["scenario_created"]["state"] == "done"
    assert steps["resource_plan"]["state"] == "pending"

    db.get(ResourcePlan, "rp-ob-1").computed_at = datetime(2026, 9, 1)
    db.commit()
    assert _status(tc)["steps"]["resource_plan"]["state"] == "done"


def test_manual_mark_skip_and_reset(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 200
    step = _status(tc)["steps"]["absences"]
    assert step["state"] == "done"
    assert step["source"] == "manual"
    assert step["marked_by"] == "Test User"
    assert step["marked_at"]

    tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "pending"})
    assert _status(tc)["steps"]["absences"]["state"] == "pending"

    tc.put("/api/v1/onboarding/team-steps/backlog", json={"team": TEAM, "state": "skipped"})
    assert _status(tc)["steps"]["backlog"]["state"] == "skipped"


def test_auto_step_cannot_be_marked_done_manually(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/backlog", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 400


def test_unknown_step_404(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/nope", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 404


def test_marks_are_per_team(client):
    tc, _ = client
    tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "done"})
    assert _status(tc, "Команда Б")["steps"]["absences"]["state"] == "pending"


def test_me_partial_update(client):
    tc, _ = client
    assert _status(tc)["me"] == {"completed_tours": [], "auto_opened": False, "hidden": False}

    resp = tc.put("/api/v1/onboarding/me", json={"auto_opened": True})
    assert resp.status_code == 200
    resp = tc.put("/api/v1/onboarding/me", json={"completed_tours": ["dashboard"]})
    assert resp.json() == {"completed_tours": ["dashboard"], "auto_opened": True, "hidden": False}
    assert _status(tc)["me"]["completed_tours"] == ["dashboard"]


def test_latch_race_is_ignored(client):
    """Строка защёлки уже есть (записал параллельный запрос) — чтение не падает."""
    tc, db = client
    db.add(TeamOnboardingMark(team=TEAM, step="scenario_created", state="done", source="auto"))
    db.commit()
    assert _status(tc)["steps"]["scenario_created"]["state"] == "done"
