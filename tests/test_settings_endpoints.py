"""Tests for settings endpoints."""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import AppSetting


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
        app.dependency_overrides.clear()


def test_generic_settings_do_not_return_jira_token(client: TestClient, db_session):
    db_session.add(AppSetting(key="jira_api_token", value="secret-token"))
    db_session.commit()

    response = client.get("/api/v1/settings/generic/jira_api_token")

    assert response.status_code == 403


def test_generic_settings_do_not_write_jira_credentials(client: TestClient):
    response = client.put(
        "/api/v1/settings/generic",
        json={"key": "jira_api_token", "value": "secret-token"},
    )

    assert response.status_code == 403


def test_generic_settings_allow_ui_and_jira_field_keys(client: TestClient):
    saved = client.put(
        "/api/v1/settings/generic",
        json={"key": "ui_team_projects", "value": "TEAM"},
    )
    assert saved.status_code == 200

    read = client.get("/api/v1/settings/generic/ui_team_projects")
    assert read.status_code == 200
    assert read.json()["value"] == "TEAM"

    saved_field = client.put(
        "/api/v1/settings/generic",
        json={"key": "jira_team_field_id", "value": "customfield_11526"},
    )
    assert saved_field.status_code == 200

    read_field = client.get("/api/v1/settings/generic/jira_team_field_id")
    assert read_field.status_code == 200
    assert read_field.json()["value"] == "customfield_11526"
