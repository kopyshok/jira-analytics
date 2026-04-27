"""Tests for GET /sync/runs and GET /sync/runs/{id} endpoints."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.repositories.sync_run import SyncRunRepository


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_list_runs_returns_recent_first(client, db_session):
    repo = SyncRunRepository(db_session)
    older = repo.create(mode="quick", trigger="scheduled")
    older.started_at = datetime.utcnow() - timedelta(hours=1)
    db_session.commit()
    newer = repo.create(mode="normal", trigger="manual")

    resp = client.get("/api/v1/sync/runs?limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == newer.id
    assert body[1]["id"] == older.id


def test_get_run_returns_stages(client, db_session):
    repo = SyncRunRepository(db_session)
    run = repo.create(mode="normal", trigger="manual")
    repo.finalize(run.id, status="ok", stages=[{"stage": "issues", "status": "ok"}])

    resp = client.get(f"/api/v1/sync/runs/{run.id}")
    assert resp.status_code == 200
    assert resp.json()["stages_json"] == [{"stage": "issues", "status": "ok"}]


def test_get_run_404_for_unknown(client, db_session):
    # Prime db_session connection so TestClient thread reuses it
    from app.models.sync_run import SyncRun
    db_session.query(SyncRun).first()

    resp = client.get("/api/v1/sync/runs/does-not-exist")
    assert resp.status_code == 404
