"""Исполнитель строки сценария: кандидаты из всех команд; ручной выбор
держится, пока в Jira не сменят исполнителя."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import ScenarioAllocation
from app.models.project import Project
from tests.services.xteam_factory import add_item, make_employee, make_issue, make_plan

PLANNING = "/api/v1/planning/scenarios"


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
def row(db_session):
    """Строка черновика команды B; в Jira исполнитель задачи — «Из Jira» (команда A)."""
    project = Project(jira_project_id="p-rfa", key="RFA", name="RFA")
    db_session.add(project)
    db_session.flush()
    jira_person = make_employee(db_session, "Из Jira", "A", jira_account_id="acc-jira")
    own = make_employee(db_session, "Свой B", "B")
    chosen = make_employee(db_session, "Выбранный", "C", jira_account_id="acc-chosen")
    issue = make_issue(db_session, project, "RFA-1")
    issue.issue_type = "RFA"
    issue.assigned_category = "initiatives_rfa"
    issue.category = "initiatives_rfa"
    issue.assignee_account_id = "acc-jira"
    issue.assignee_display_name = "Из Jira"
    sc, _plan = make_plan(db_session, "B", scenario_status="draft")
    item = add_item(db_session, sc, "RFA-1", issue=issue, assignee=jira_person)
    alloc = (
        db_session.query(ScenarioAllocation)
        .filter_by(scenario_id=sc.id, backlog_item_id=item.id)
        .one()
    )
    db_session.commit()
    return SimpleNamespace(
        sc=sc, item=item, alloc=alloc, issue=issue,
        jira=jira_person, own=own, chosen=chosen,
    )


def test_scenario_candidates_from_all_teams(client, row):
    r = client.get(
        f"{PLANNING}/{row.sc.id}/assignee-candidates",
        params={"backlog_item_id": row.item.id},
    )

    assert r.status_code == 200, r.text
    groups = {g["key"]: g for g in r.json()}
    assert [c["employee_id"] for c in groups["jira"]["employees"]] == [row.jira.id]
    assert groups["jira"]["employees"][0]["team"] == "A"
    assert [c["employee_id"] for c in groups["team"]["employees"]] == [row.own.id]
    assert [c["employee_id"] for c in groups["other"]["employees"]] == [row.chosen.id]


def test_scenario_candidates_unknown_item_is_404(client, row):
    r = client.get(
        f"{PLANNING}/{row.sc.id}/assignee-candidates", params={"backlog_item_id": "nope"}
    )
    assert r.status_code == 404
