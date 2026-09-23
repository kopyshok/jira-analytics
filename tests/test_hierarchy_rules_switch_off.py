"""Включение правила «Эпик внутри RFA» выключает галочку «В план» у ставших служебными."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import BacklogService


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db, *, rule_enabled: bool) -> tuple[str, str]:
    rule = HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                         require_parent=True, is_container=False, is_enabled=rule_enabled, description="svc")
    db.add_all([rule, Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA")])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
        PlanningScenario(id="s-draft", name="draft", year=2026, quarter="Q4", status="draft", team="T1"),
    ])
    db.flush()
    svc = BacklogService(db)
    svc.sync_from_issue(db.get(Issue, "i-rfa"))
    svc.sync_from_issue(db.get(Issue, "i-disc"))
    disc_id = db.query(BacklogItem.id).filter_by(issue_id="i-disc").scalar()
    db.commit()
    return rule.id, disc_id


def test_enabling_rule_switches_off_new_service_epics(client, testclient_db_session):
    db = testclient_db_session
    rule_id, disc_id = _seed(db, rule_enabled=False)
    db.add(ScenarioAllocation(scenario_id="s-draft", backlog_item_id=disc_id, included_flag=False,
                              planned_hours=0, sort_order=99.0))
    db.commit()
    assert db.get(BacklogItem, disc_id).included_in_planning is True

    r = client.patch(f"/api/v1/hierarchy-rules/{rule_id}", json={"is_enabled": True})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(BacklogItem, disc_id).included_in_planning is False
    assert db.query(ScenarioAllocation).filter_by(scenario_id="s-draft", backlog_item_id=disc_id).count() == 0


def test_rule_edit_keeps_pm_choice_on_existing_service_epic(client, testclient_db_session):
    db = testclient_db_session
    rule_id, disc_id = _seed(db, rule_enabled=True)
    db.get(BacklogItem, disc_id).included_in_planning = True  # PM включил сам
    db.commit()

    r = client.patch(f"/api/v1/hierarchy-rules/{rule_id}", json={"description": "Дискавери"})
    assert r.status_code == 200, r.text

    db.expire_all()
    assert db.get(BacklogItem, disc_id).included_in_planning is True


def test_creating_service_rule_switches_off_existing_epics(client, testclient_db_session):
    db = testclient_db_session
    _rule_id, disc_id = _seed(db, rule_enabled=False)
    r = client.post("/api/v1/hierarchy-rules", json={
        "priority": 1, "project_key": "RFA", "issue_type": "Эпик",
        "require_parent": True, "is_container": False,
    })
    assert r.status_code == 201, r.text
    db.expire_all()
    assert db.get(BacklogItem, disc_id).included_in_planning is False
