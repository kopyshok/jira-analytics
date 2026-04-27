"""Tests for sync schedule CRUD API (T22)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.repositories.sync_schedule import SyncScheduleRepository

import app.models as _app_models  # noqa: F401 — ensure all models are registered for Base.metadata


@pytest.fixture
def schedule_db():
    """In-memory SQLite engine with StaticPool so TestClient worker thread shares the same connection."""
    _engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=_engine)
    _Session = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    session = _Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def client(schedule_db):
    def override_get_db():
        yield schedule_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed_schedules(schedule_db):
    repo = SyncScheduleRepository(schedule_db)
    repo.create(name="daily_incremental", cron_expr="0 6 * * *", mode="normal")
    repo.create(name="worklogs_workhours", cron_expr="0 8-20/2 * * 1-5", mode="quick")
    repo.create(name="weekly_full", cron_expr="0 3 * * 0", mode="full")
    return repo


# ------------------------------------------------------------------
# T22-a: list
# ------------------------------------------------------------------

def test_list_returns_seeded(client, schedule_db):
    _seed_schedules(schedule_db)

    resp = client.get("/api/v1/sync/schedule")
    assert resp.status_code == 200
    body = resp.json()
    names = {s["name"] for s in body}
    assert {"daily_incremental", "worklogs_workhours", "weekly_full"}.issubset(names)


# ------------------------------------------------------------------
# T22-b: patch updates cron and enabled
# ------------------------------------------------------------------

def test_patch_updates_cron_and_enabled(client, schedule_db):
    repo = _seed_schedules(schedule_db)
    item = repo.list_all()[0]
    original_id = item.id

    resp = client.patch(
        f"/api/v1/sync/schedule/{original_id}",
        json={"cron_expr": "0 7 * * *", "enabled": False},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cron_expr"] == "0 7 * * *"
    assert body["enabled"] is False


# ------------------------------------------------------------------
# T22-c: invalid cron → 400
# ------------------------------------------------------------------

def test_patch_invalid_cron_400(client, schedule_db):
    repo = _seed_schedules(schedule_db)
    item = repo.list_all()[0]

    resp = client.patch(
        f"/api/v1/sync/schedule/{item.id}",
        json={"cron_expr": "not a cron"},
    )
    assert resp.status_code == 400


def test_create_invalid_cron_400(client):
    resp = client.post(
        "/api/v1/sync/schedule",
        json={"name": "bad_cron", "cron_expr": "invalid", "mode": "quick"},
    )
    assert resp.status_code == 400


# ------------------------------------------------------------------
# T22-d: create and delete custom
# ------------------------------------------------------------------

def test_create_and_delete_custom(client):
    resp = client.post(
        "/api/v1/sync/schedule",
        json={"name": "my_custom", "cron_expr": "*/30 * * * *", "mode": "quick", "enabled": True},
    )
    assert resp.status_code == 201
    schedule_id = resp.json()["id"]

    # Убедимся что появился в списке
    list_resp = client.get("/api/v1/sync/schedule")
    names = {s["name"] for s in list_resp.json()}
    assert "my_custom" in names

    # Удаляем
    del_resp = client.delete(f"/api/v1/sync/schedule/{schedule_id}")
    assert del_resp.status_code == 204

    # Проверяем что исчез
    list_resp2 = client.get("/api/v1/sync/schedule")
    names2 = {s["name"] for s in list_resp2.json()}
    assert "my_custom" not in names2


# ------------------------------------------------------------------
# T22-e: 404 for unknown id
# ------------------------------------------------------------------

def test_patch_404_for_unknown(client):
    resp = client.patch(
        "/api/v1/sync/schedule/does-not-exist",
        json={"enabled": False},
    )
    assert resp.status_code == 404


def test_delete_404_for_unknown(client):
    resp = client.delete("/api/v1/sync/schedule/does-not-exist")
    assert resp.status_code == 404
