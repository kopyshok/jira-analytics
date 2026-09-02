"""Отсечка ОПЭ сохраняется как общая настройка сервиса."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.services import opo_policy


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_cutoff_saved_and_read_back(client):
    r = client.put(
        "/api/v1/settings/generic",
        json={"key": opo_policy.SETTING_KEY, "value": "2026Q4"},
    )
    assert r.status_code == 200

    r = client.get(f"/api/v1/settings/generic/{opo_policy.SETTING_KEY}")
    assert r.status_code == 200
    assert r.json()["value"] == "2026Q4"
