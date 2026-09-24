"""Исполнитель строки сценария: кандидаты из всех команд; ручной выбор
держится, пока в Jira не сменят исполнителя."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, ScenarioAllocation
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


def _choose(client, row, employee_id):
    return client.patch(
        f"{PLANNING}/{row.sc.id}/allocations/{row.alloc.id}/assignee",
        json={"assignee_employee_id": employee_id},
    )


def test_manual_choice_from_other_team_is_remembered(client, db_session, row):
    r = _choose(client, row, row.chosen.id)

    assert r.status_code == 200, r.text
    assert r.json()["assignee_employee_id"] == row.chosen.id
    assert r.json()["assignee_display_name"] == "Выбранный"
    db_session.expire_all()
    item = db_session.get(BacklogItem, row.item.id)
    assert item.assignee_manual is True
    assert item.assignee_jira_account_at_choice == "acc-jira"


def test_choosing_jira_assignee_follows_jira_again(client, db_session, row):
    _choose(client, row, row.chosen.id)

    r = _choose(client, row, row.jira.id)

    assert r.status_code == 200, r.text
    db_session.expire_all()
    item = db_session.get(BacklogItem, row.item.id)
    assert item.assignee_manual is False
    assert item.assignee_jira_account_at_choice is None


def test_manual_choice_survives_refresh_until_jira_changes(client, db_session, row, monkeypatch):
    from app.api.endpoints import backlog as backlog_ep

    jira = {"account": "acc-jira"}

    class _FakeJira:
        @classmethod
        def from_db(cls, db):
            return cls()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

    async def fake_refresh(self, keys, extra_field_ids=None, on_issue=None, on_progress=None):
        issues = db_session.query(Issue).filter(Issue.key.in_(keys)).all()
        for issue in issues:
            fields = SimpleNamespace(
                assignee=SimpleNamespace(accountId=jira["account"]), _extra={},
            )
            on_issue(SimpleNamespace(fields=fields), issue)
        return len(issues), len(issues)

    monkeypatch.setattr(backlog_ep, "JiraClient", _FakeJira)
    monkeypatch.setattr(backlog_ep, "_discover_field_id", AsyncMock(return_value=None))
    monkeypatch.setattr(backlog_ep.SyncService, "refresh_issues_by_keys", fake_refresh)
    _choose(client, row, row.chosen.id)

    assert client.post("/api/v1/backlog/refresh-from-jira").status_code == 200
    db_session.expire_all()
    assert db_session.get(BacklogItem, row.item.id).assignee_employee_id == row.chosen.id

    # В Jira сменили исполнителя — ручной выбор больше не действует.
    newcomer = make_employee(db_session, "Новый в Jira", "B", jira_account_id="acc-new")
    db_session.commit()
    jira["account"] = "acc-new"
    assert client.post("/api/v1/backlog/refresh-from-jira").status_code == 200
    db_session.expire_all()
    item = db_session.get(BacklogItem, row.item.id)
    assert item.assignee_employee_id == newcomer.id
    assert item.assignee_manual is False
