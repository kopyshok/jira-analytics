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
