"""Ручные часы задачи (Issue) сразу видны в строке бэклога.

Регресс: правка через /issues/{id}/plan писала только
Issue.planned_<role>_hours_manual, а список бэклога, сценарии и ресурсный план
читают копию BacklogItem.estimate_<role>_hours, которая обновлялась лишь при
синке. Спека: docs/superpowers/specs/2026-09-23-planning-q4-design.md, п. 1.5.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, Project
from app.services.backlog_service import BACKLOG_CATEGORY, BacklogService
from app.services.event_bus import get_event_bus


def _seed(db, key="PS-1", **issue_kwargs):
    """Jira-задача категории «Инициативы RFA» + её строка бэклога.

    Копия часов в строке совпадает с действующими часами задачи — как после синка.
    """
    p = Project(id=f"p-{key}", key=key.split("-")[0], jira_project_id=f"jp-{key}", name=f"Project {key}")
    db.add(p)
    db.flush()
    issue = Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}",
        summary=f"Summary {key}", issue_type="RFA", status="Open",
        project_id=p.id, category=BACKLOG_CATEGORY, **issue_kwargs,
    )
    db.add(issue)
    db.flush()
    item = BacklogItem(
        issue_id=issue.id, title=issue.summary, project_id=p.id,
        estimate_analyst_hours=issue.planned_analyst_hours,
        estimate_dev_hours=issue.planned_dev_hours,
        estimate_qa_hours=issue.planned_qa_hours,
        estimate_opo_hours=issue.planned_opo_hours,
    )
    item.estimate_hours = sum(
        v or 0 for v in (
            item.estimate_analyst_hours, item.estimate_dev_hours,
            item.estimate_qa_hours, item.estimate_opo_hours,
        )
    ) or None
    db.add(item)
    db.commit()
    return issue.id, item.id


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def client(testclient_db_session, bus):
    def _override():
        yield testclient_db_session
    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_event_bus] = lambda: bus
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_event_bus, None)


def _item(db, item_id) -> BacklogItem:
    db.expire_all()
    return db.get(BacklogItem, item_id)


def test_plan_edit_updates_backlog_copy_and_total(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(db, planned_analyst_hours_jira=100, planned_dev_hours_jira=500)

    r = client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "уточнили"},
    )
    assert r.status_code == 200, r.text

    item = _item(db, item_id)
    assert item.estimate_dev_hours == 600
    assert item.estimate_analyst_hours == 100
    assert item.estimate_hours == 700


def test_plan_revert_restores_backlog_copy(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(db, key="PS-2", planned_dev_hours_jira=500)
    client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "x"},
    )

    r = client.post(f"/api/v1/issues/{issue_id}/plan/revert", json={})
    assert r.status_code == 200, r.text

    item = _item(db, item_id)
    assert item.estimate_dev_hours == 500
    assert item.estimate_hours == 500


def test_conflict_accept_jira_updates_backlog_copy(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(
        db, key="PS-3", planned_dev_hours_jira=500, planned_dev_hours_manual=600,
    )
    assert _item(db, item_id).estimate_dev_hours == 600

    r = client.post(
        f"/api/v1/issues/{issue_id}/plan/conflict-resolve",
        json={"action": "accept_jira", "role": "dev"},
    )
    assert r.status_code == 200, r.text

    assert _item(db, item_id).estimate_dev_hours == 500


def test_plan_edit_publishes_backlog_event(client, testclient_db_session, bus):
    db = testclient_db_session
    issue_id, _ = _seed(db, key="PS-4", planned_dev_hours_jira=500)

    client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "x"},
    )
    client.post(f"/api/v1/issues/{issue_id}/plan/revert", json={})
    client.post(
        f"/api/v1/issues/{issue_id}/plan/conflict-resolve",
        json={"action": "ignore", "role": "dev"},
    )

    expected = {"type": "entity_changed", "entities": ["issues", "backlog"]}
    assert bus.publish.await_count == 3
    for call in bus.publish.await_args_list:
        assert call.args[0] == expected


def test_plan_edit_without_backlog_item_is_ok(client, testclient_db_session):
    """Задача вне бэклога (например, обычная задача в дереве) — правка работает,
    строк бэклога не появляется."""
    db = testclient_db_session
    p = Project(id="p-PS5", key="PS5", jira_project_id="jp-PS5", name="P5")
    db.add(p)
    db.flush()
    issue = Issue(
        id="i-PS5", key="PS5-1", jira_issue_id="j-PS5", summary="s",
        issue_type="Task", status="Open", project_id=p.id,
        category="development", planned_dev_hours_jira=10,
    )
    db.add(issue)
    db.commit()

    r = client.patch(
        f"/api/v1/issues/{issue.id}/plan",
        json={"role_hours": {"dev": 20}, "comment": "x"},
    )
    assert r.status_code == 200, r.text
    assert db.query(BacklogItem).filter_by(issue_id=issue.id).count() == 0


def test_inline_estimate_goes_to_issue_and_survives_sync(client, testclient_db_session, bus):
    db = testclient_db_session
    issue_id, item_id = _seed(db, key="PS-6", planned_dev_hours_jira=500)

    r = client.patch(f"/api/v1/backlog/{item_id}", json={"estimate_dev_hours": 700})
    assert r.status_code == 200, r.text
    assert r.json()["estimate_dev_hours"] == 700
    # Изменилась и сама задача — событие несёт обе сущности.
    bus.publish.assert_awaited_once_with(
        {"type": "entity_changed", "entities": ["issues", "backlog"]}
    )

    db.expire_all()
    issue = db.get(Issue, issue_id)
    assert issue.planned_dev_hours_manual == 700
    assert issue.planned_dev_hours_jira == 500

    # Синк больше не затирает ручную правку копией из Jira.
    BacklogService(db).sync_from_issue(issue)
    db.commit()
    item = _item(db, item_id)
    assert item.estimate_dev_hours == 700
    assert item.estimate_hours == 700


def test_inline_estimate_null_returns_to_jira(client, testclient_db_session):
    db = testclient_db_session
    issue_id, item_id = _seed(
        db, key="PS-7", planned_dev_hours_jira=500, planned_dev_hours_manual=700,
    )

    r = client.patch(f"/api/v1/backlog/{item_id}", json={"estimate_dev_hours": None})
    assert r.status_code == 200, r.text
    assert r.json()["estimate_dev_hours"] == 500
    db.expire_all()
    assert db.get(Issue, issue_id).planned_dev_hours_manual is None


def test_inline_estimate_on_manual_idea_writes_directly(client, testclient_db_session):
    """Ручная идея без Jira-задачи — часы по-прежнему пишутся в саму строку."""
    db = testclient_db_session
    item = BacklogItem(title="Идея")
    db.add(item)
    db.commit()

    r = client.patch(f"/api/v1/backlog/{item.id}", json={"estimate_dev_hours": 10})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estimate_dev_hours"] == 10
    assert body["estimate_hours"] == 10


def test_backlog_response_carries_jira_hours(client, testclient_db_session):
    db = testclient_db_session
    _, item_id = _seed(
        db, key="PS-8", planned_dev_hours_jira=500, planned_dev_hours_manual=700,
    )
    body = client.get(f"/api/v1/backlog/{item_id}").json()
    assert body["estimate_dev_hours"] == 700
    assert body["estimate_dev_hours_jira"] == 500
    assert body["estimate_analyst_hours_jira"] is None


def test_inline_estimate_with_other_fields_keeps_them(client, testclient_db_session):
    """Часы и вовлечённость одним запросом: выравнивание по задаче не затирает
    вовлечённость, пришедшую в этом же запросе."""
    db = testclient_db_session
    _, item_id = _seed(db, key="PS-9", planned_dev_hours_jira=500, involvement_dev=0.5)

    r = client.patch(
        f"/api/v1/backlog/{item_id}",
        json={"estimate_dev_hours": 700, "involvement_dev": 0.8},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estimate_dev_hours"] == 700
    assert body["involvement_dev"] == 0.8


def test_inline_estimate_on_manual_idea_publishes_backlog_only(client, testclient_db_session, bus):
    db = testclient_db_session
    item = BacklogItem(title="Идея-2")
    db.add(item)
    db.commit()

    client.patch(f"/api/v1/backlog/{item.id}", json={"estimate_dev_hours": 10})
    bus.publish.assert_awaited_once_with({"type": "entity_changed", "entities": ["backlog"]})


def test_plan_edit_on_archived_row_keeps_it_archived(client, testclient_db_session):
    """Строка в архиве остаётся в архиве и не попадает в черновики сценариев,
    но копия часов выравнивается по задаче."""
    from datetime import datetime

    from app.models import PlanningScenario, ScenarioAllocation

    db = testclient_db_session
    issue_id, item_id = _seed(db, key="PS-10", planned_dev_hours_jira=500)
    archived_at = datetime(2026, 9, 1)
    item = db.get(BacklogItem, item_id)
    item.archived_at = archived_at
    db.add(PlanningScenario(name="Черновик", status="draft"))
    db.commit()

    r = client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "x"},
    )
    assert r.status_code == 200, r.text

    item = _item(db, item_id)
    assert item.archived_at == archived_at
    assert item.estimate_dev_hours == 600
    assert item.estimate_hours == 600
    assert db.query(ScenarioAllocation).filter_by(backlog_item_id=item_id).count() == 0


def test_plan_edit_after_issue_left_backlog_updates_hours(client, testclient_db_session):
    """Задача ушла из категории бэклога (строка уходит в архив) — часы в строке
    всё равно равны действующим часам задачи."""
    db = testclient_db_session
    issue_id, item_id = _seed(db, key="PS-11", planned_dev_hours_jira=500)
    issue = db.get(Issue, issue_id)
    issue.category = "development"
    db.commit()

    r = client.patch(
        f"/api/v1/issues/{issue_id}/plan",
        json={"role_hours": {"dev": 600}, "comment": "x"},
    )
    assert r.status_code == 200, r.text

    item = _item(db, item_id)
    assert item.archived_at is not None
    assert item.estimate_dev_hours == 600
    assert item.estimate_hours == 600
