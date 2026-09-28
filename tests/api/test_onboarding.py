"""«Первые шаги»: статус шагов команды, защёлка, ручные отметки, личное состояние."""
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

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
from app.services import onboarding_service as svc

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


def test_backlog_excludes_jira_done_like_archive_tab(client):
    """Инициатива из Jira в статусе done не должна засчитываться — как во
    вкладке «Архив» бэклога (см. app/api/endpoints/backlog.py). Проверяем на
    двух разных командах, чтобы не упереться в защёлку: один раз шаг уже
    закрылся — назад в pending он не откатится, даже если данные исчезнут."""
    tc, db = client
    _project(db)

    active_issue = _issue(db, 50, category="initiatives_rfa", team="Команда В")
    db.add(BacklogItem(id="bl-ob-active", title="Инициатива", issue_id=active_issue.id, estimate_dev_hours=40))
    db.commit()
    assert _status(tc, "Команда В")["steps"]["backlog"]["state"] == "done"

    done_issue = _issue(db, 51, category="initiatives_rfa", team="Команда Г")
    done_issue.status_category = "done"
    db.add(BacklogItem(id="bl-ob-done", title="Инициатива", issue_id=done_issue.id, estimate_dev_hours=40))
    db.commit()
    assert _status(tc, "Команда Г")["steps"]["backlog"]["state"] == "pending"


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


def test_auto_step_relatches_after_manual_reset(client):
    """Авто-шаг сброшен в pending через PUT — при следующем чтении, пока условие
    ещё выполняется, он снова защёлкивается как done/auto."""
    tc, db = client
    db.add(PlanningScenario(id="sc-relatch-1", name="2026 Q4", team=TEAM, quarter="Q4", year=2026))
    db.commit()
    assert _status(tc)["steps"]["scenario_created"]["state"] == "done"

    resp = tc.put("/api/v1/onboarding/team-steps/scenario_created", json={"team": TEAM, "state": "pending"})
    assert resp.status_code == 200

    step = _status(tc)["steps"]["scenario_created"]
    assert step["state"] == "done"
    assert step["source"] == "auto"


def test_skipped_auto_step_stays_skipped_when_condition_holds(client):
    """Авто-шаг явно пропущен — не должен перезащёлкиваться в done, даже если
    условие выполняется."""
    tc, db = client
    db.add(PlanningScenario(id="sc-skip-1", name="2026 Q4", team=TEAM, quarter="Q4", year=2026))
    db.commit()

    resp = tc.put("/api/v1/onboarding/team-steps/scenario_created", json={"team": TEAM, "state": "skipped"})
    assert resp.status_code == 200

    step = _status(tc)["steps"]["scenario_created"]
    assert step["state"] == "skipped"
    assert step["source"] == "manual"


def test_manual_mark_skip_and_reset(client):
    tc, _ = client
    resp = tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 200
    step = _status(tc)["steps"]["absences"]
    assert step["state"] == "done"
    assert step["source"] == "manual"
    assert step["marked_by"] == "Test User"
    assert step["marked_at"]

    resp = tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "pending"})
    assert resp.status_code == 200
    assert _status(tc)["steps"]["absences"]["state"] == "pending"

    resp = tc.put("/api/v1/onboarding/team-steps/backlog", json={"team": TEAM, "state": "skipped"})
    assert resp.status_code == 200
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
    resp = tc.put("/api/v1/onboarding/team-steps/absences", json={"team": TEAM, "state": "done"})
    assert resp.status_code == 200
    assert _status(tc, "Команда Б")["steps"]["absences"]["state"] == "pending"


def test_me_partial_update(client):
    tc, _ = client
    assert _status(tc)["me"] == {"completed_tours": [], "auto_opened": False, "hidden": False}

    resp = tc.put("/api/v1/onboarding/me", json={"auto_opened": True})
    assert resp.status_code == 200
    resp = tc.put("/api/v1/onboarding/me", json={"completed_tours": ["dashboard"]})
    assert resp.status_code == 200
    assert resp.json() == {"completed_tours": ["dashboard"], "auto_opened": True, "hidden": False}
    assert _status(tc)["me"]["completed_tours"] == ["dashboard"]


def test_latch_race_is_ignored(client, monkeypatch):
    """Пока считаем условие шага, параллельный запрос успевает сам вставить и
    закоммитить свою авто-отметку по этому же шагу — наш ``_latch`` должен
    просто откатиться на IntegrityError, а не уронить запрос."""
    tc, db = client
    db.add(PlanningScenario(id="sc-race-1", name="2026 Q4", team=TEAM, quarter="Q4", year=2026))
    db.commit()

    def racing(db_inner, team):
        # Отдельная сессия на том же соединении: в тестовом SQLite используется
        # StaticPool с одним соединением на процесс, поэтому запись отдельной
        # сессии сразу видна остальным — этим имитируем параллельный запрос.
        other = Session(bind=db_inner.get_bind())
        try:
            other.add(TeamOnboardingMark(team=team, step="scenario_created", state="done", source="auto"))
            other.commit()
        finally:
            other.close()
        return True

    monkeypatch.setitem(svc.AUTO_STEPS, "scenario_created", racing)
    steps = svc.team_steps(db, TEAM)
    assert steps["scenario_created"]["state"] == "done"


def test_status_survives_concurrent_manual_mark_delete(client, monkeypatch):
    """Пока идёт проверка условий других шагов, параллельный запрос удаляет
    ручную отметку («Вернуть» по другому шагу). До фикса марки грузились один
    раз в начале team_steps, а `_latch` своим commit протухал уже загруженные
    объекты (expire_on_commit) — обращение к удалённой строке падало с
    ObjectDeletedError. Ответ должен строиться по свежему чтению без падения."""
    tc, db = client
    db.add(TeamOnboardingMark(
        team=TEAM, step="absences", state="done", source="manual", marked_at=datetime.utcnow(),
    ))
    db.commit()

    def deletes_other_mark_and_latches(db_inner, team):
        other = Session(bind=db_inner.get_bind())
        try:
            other.query(TeamOnboardingMark).filter(
                TeamOnboardingMark.team == team, TeamOnboardingMark.step == "absences"
            ).delete()
            other.commit()
        finally:
            other.close()
        return True

    monkeypatch.setitem(svc.AUTO_STEPS, "team_roles", deletes_other_mark_and_latches)
    steps = svc.team_steps(db, TEAM)
    assert steps["absences"]["state"] == "pending"
    assert steps["team_roles"]["state"] == "done"
