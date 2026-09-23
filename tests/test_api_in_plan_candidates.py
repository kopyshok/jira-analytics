"""Галочка «В план» решает кандидатство во всех местах отбора сценария.

Покрывает тесты из спеки: служебный эпик не в черновике; включение добавляет
его сверх родителя в режиме «целиком»; выключение обычной задачи убирает её
из черновиков и не трогает утверждённые; дочки «по эпикам» с False — не кандидаты.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation
from app.services.backlog_service import BacklogService
from app.services.event_bus import get_event_bus


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def client(testclient_db_session, bus):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_rfa_with_discovery(db) -> dict[str, str]:
    db.add_all([
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=True, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
    ])
    db.flush()
    db.add_all([
        Issue(id="i-rfa", key="RFA-1", jira_issue_id="j1", summary="RFA", issue_type="RFA",
              status="Open", project_id="p-rfa", category="initiatives_rfa", team="T1"),
        Issue(id="i-disc", key="RFA-2", jira_issue_id="j2", summary="Дискавери", issue_type="Эпик",
              status="Open", project_id="p-rfa", parent_id="i-rfa", category="initiatives_rfa", team="T1"),
    ])
    db.flush()
    svc = BacklogService(db)
    svc.sync_from_issue(db.get(Issue, "i-rfa"))
    svc.sync_from_issue(db.get(Issue, "i-disc"))
    db.commit()
    return {bi.issue_id: bi.id for bi in db.query(BacklogItem).all()}


def _create_scenario(client) -> str:
    r = client.post("/api/v1/planning/scenarios", json={"name": "Q4", "year": 2026, "quarter": 4, "team": "T1"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _alloc_ids(client, sid: str) -> set[str]:
    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    return {a["backlog_item_id"] for a in r.json()}


def test_service_epic_off_is_not_candidate(client, testclient_db_session):
    ids = _seed_rfa_with_discovery(testclient_db_session)
    sid = _create_scenario(client)
    got = _alloc_ids(client, sid)
    assert ids["i-rfa"] in got
    assert ids["i-disc"] not in got


def test_turning_service_epic_on_adds_it_on_top_of_whole_parent(client, testclient_db_session):
    ids = _seed_rfa_with_discovery(testclient_db_session)
    sid = _create_scenario(client)
    r = client.patch(f"/api/v1/backlog/{ids['i-disc']}/included", json={"included": True})
    assert r.status_code == 200, r.text
    got = _alloc_ids(client, sid)
    assert ids["i-disc"] in got, "включённое Дискавери — в черновике"
    assert ids["i-rfa"] in got, "RFA целиком остаётся — Дискавери сверх неё"
    # Досинк сценария тоже не выкидывает его.
    r = client.post(f"/api/v1/planning/scenarios/{sid}/sync-backlog")
    assert r.status_code == 200, r.text
    assert ids["i-disc"] in {a["backlog_item_id"] for a in r.json()}


def test_turning_regular_item_off_removes_from_drafts_keeps_approved(client, testclient_db_session):
    db = testclient_db_session
    db.add(Project(id="p1", key="PRJ", jira_project_id="jp1", name="Project"))
    db.flush()
    db.add(Issue(id="i-one", key="PRJ-1", jira_issue_id="jx", summary="Инициатива", issue_type="RFA",
                 status="Open", project_id="p1", category="initiatives_rfa", team="T1"))
    db.flush()
    BacklogService(db).sync_from_issue(db.get(Issue, "i-one"))
    db.commit()
    item_id = db.query(BacklogItem.id).filter_by(issue_id="i-one").scalar()
    sid = _create_scenario(client)
    db.add(PlanningScenario(id="s-appr", name="appr", year=2026, quarter="Q3", status="approved", team="T1"))
    db.flush()
    db.add(ScenarioAllocation(scenario_id="s-appr", backlog_item_id=item_id, included_flag=False,
                              planned_hours=0, sort_order=1.0))
    db.commit()

    r = client.patch(f"/api/v1/backlog/{item_id}/included", json={"included": False})
    assert r.status_code == 200, r.text

    assert item_id not in _alloc_ids(client, sid), "self-heal не возвращает выключенную"
    db.expire_all()
    assert db.query(ScenarioAllocation).filter_by(scenario_id="s-appr", backlog_item_id=item_id).count() == 1


def test_by_epics_child_off_is_not_candidate(client, testclient_db_session):
    db = testclient_db_session
    db.add(Project(id="p1", key="PRJ", jira_project_id="jp1", name="Project"))
    db.flush()
    db.add_all([
        Issue(id="i-p", key="PRJ-1", jira_issue_id="jp", summary="RFA", issue_type="RFA",
              status="Open", project_id="p1", category="initiatives_rfa", team="T1"),
        Issue(id="i-c", key="PRJ-2", jira_issue_id="jc", summary="Эпик", issue_type="Epic",
              status="Open", project_id="p1", parent_id="i-p", category="initiatives_rfa", team="T1"),
    ])
    db.add_all([
        BacklogItem(id="bi-p", issue_id="i-p", title="RFA", priority=1),
        BacklogItem(id="bi-c", issue_id="i-c", title="Эпик", priority=2),
    ])
    db.commit()
    assert client.patch("/api/v1/backlog/bi-p/planning-mode", json={"mode": "by_epics"}).status_code == 200
    assert client.patch("/api/v1/backlog/bi-c/included", json={"included": False}).status_code == 200
    sid = _create_scenario(client)
    assert "bi-c" not in _alloc_ids(client, sid)


def test_toggle_publishes_backlog_and_planning(client, testclient_db_session, bus):
    ids = _seed_rfa_with_discovery(testclient_db_session)
    bus.publish.reset_mock()
    client.patch(f"/api/v1/backlog/{ids['i-disc']}/included", json={"included": True})
    bus.publish.assert_called_once_with({"type": "entity_changed", "entities": ["backlog", "planning"]})
