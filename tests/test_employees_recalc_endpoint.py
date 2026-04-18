"""Tests for POST /employees/recalc-active endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Category


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_post_recalc_active_returns_stats(client, db_session):
    # Category model uses `label` and `is_system`, not `name`/`is_builtin`.
    db_session.add_all([
        Category(id="c1", code="active_1", label="Active1", is_system=False),
        Category(id="c2", code="archive", label="Archive", is_system=True),
    ])
    db_session.commit()
    # Pin connection for in-memory SQLite (SingletonThreadPool quirk:
    # pre-query on the main thread so the Session caches the populated
    # connection before the endpoint handler touches it).
    db_session.query(Category).first()

    resp = client.post("/api/v1/employees/recalc-active")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"activated", "deactivated", "total_active"}
    assert all(isinstance(body[k], int) for k in body)
