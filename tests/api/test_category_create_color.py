"""Tests for auto color assignment on POST /categories."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.api.endpoints.categories import _AUTO_COLOR_PALETTE
from app.models.category import Category


@pytest.fixture
def db():
    import app.models  # noqa: F401 — register all models
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_create_without_color_gets_auto_color(client):
    resp = client.post("/api/v1/categories", json={"code": "c1", "label": "Cat 1"})
    assert resp.status_code == 201
    color = resp.json()["color"]
    assert color in _AUTO_COLOR_PALETTE


def test_create_with_explicit_color_keeps_it(client):
    resp = client.post(
        "/api/v1/categories",
        json={"code": "c2", "label": "Cat 2", "color": "#123456"},
    )
    assert resp.status_code == 201
    assert resp.json()["color"] == "#123456"


def test_auto_colors_do_not_repeat_until_palette_exhausted(client):
    seen = []
    for i in range(len(_AUTO_COLOR_PALETTE)):
        resp = client.post(
            "/api/v1/categories", json={"code": f"auto{i}", "label": f"Auto {i}"}
        )
        assert resp.status_code == 201
        seen.append(resp.json()["color"])
    assert sorted(seen) == sorted(_AUTO_COLOR_PALETTE)
