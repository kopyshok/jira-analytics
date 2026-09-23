"""POST /issues/{id}/plan/choice."""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Issue, Project
from app.services.event_bus import get_event_bus

SOURCES = {"dev": [
    {"source": "customfield_12432", "label": "Разработка (ч)", "value": 100.0},
    {"source": "customfield_14648", "label": "Оценка 1С (ч)", "value": 120.0},
]}


@pytest.fixture
def client(testclient_db_session):
    bus = AsyncMock()
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    app.dependency_overrides[get_event_bus] = lambda: bus
    yield TestClient(app), bus
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_event_bus, None)


def _seed(db):
    p = Project(id="p-pc", key="PC", jira_project_id="jp-pc", name="PC")
    i = Issue(
        id="i-pc", key="PC-1", jira_issue_id="j-pc", summary="S",
        issue_type="RFA", status="Open", project_id=p.id,
        planned_dev_hours_jira=100.0, planned_hours_sources=SOURCES,
    )
    db.add_all([p, i])
    db.commit()


def test_choice_source(client, testclient_db_session):
    c, bus = client
    _seed(testclient_db_session)
    r = c.post("/api/v1/issues/i-pc/plan/choice",
               json={"role": "dev", "source": "customfield_14648"})
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["dev"] == 120.0
    bus.publish.assert_awaited()


def test_choice_manual(client, testclient_db_session):
    c, _ = client
    _seed(testclient_db_session)
    r = c.post("/api/v1/issues/i-pc/plan/choice", json={"role": "dev", "manual_value": 110})
    assert r.status_code == 200, r.text
    assert r.json()["plan"]["dev"] == 110.0


@pytest.mark.parametrize("body", [
    {"role": "dev"},
    {"role": "dev", "source": "customfield_12432", "manual_value": 5},
    {"role": "dev", "source": "customfield_404"},
    {"role": "boss", "source": "customfield_12432"},
    {"role": "dev", "manual_value": -1},
])
def test_choice_invalid(client, testclient_db_session, body):
    c, _ = client
    _seed(testclient_db_session)
    assert c.post("/api/v1/issues/i-pc/plan/choice", json=body).status_code == 422


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_choice_manual_non_finite_is_422(client, testclient_db_session, raw):
    c, _ = client
    _seed(testclient_db_session)
    r = c.post(
        "/api/v1/issues/i-pc/plan/choice",
        content=f'{{"role": "dev", "manual_value": {raw}}}',
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert testclient_db_session.get(Issue, "i-pc").planned_dev_hours_manual is None


def test_choice_404(client):
    c, _ = client
    r = c.post("/api/v1/issues/missing/plan/choice", json={"role": "dev", "source": "x"})
    assert r.status_code == 404
