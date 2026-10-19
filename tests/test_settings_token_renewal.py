"""Настройки: состояние самопродления токенов и сброс при ручной замене."""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting
from app.services import token_renewal


def _put(db, key, value):
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def _client(db):
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_status_endpoint(db_session, monkeypatch):
    monkeypatch.setattr(token_renewal, "get_settings", lambda: SimpleNamespace(token_auto_renew=True))
    _put(db_session, "jira_api_token", "tok")
    _put(db_session, "jira_token_renewal", json.dumps({"expires_at": "2026-11-02T12:00:00+00:00"}))
    _put(db_session, "confluence_api_token", None)
    try:
        got = _client(db_session).get("/api/v1/settings/token-renewal")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert got.status_code == 200
    body = got.json()
    assert body["enabled"] is True
    assert body["jira"]["expires_at"] == "2026-11-02T12:00:00+00:00"
    assert body["confluence"] is None


def test_manual_jira_token_resets_renewal_state(db_session):
    _put(db_session, "jira_token_renewal", json.dumps({"id": 5, "expires_at": "2026-11-02T12:00:00+00:00"}))
    try:
        put = _client(db_session).put("/api/v1/settings/jira", json={"api_token": "manual"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert token_renewal.load_state(db_session, "jira") == {}


def test_manual_confluence_token_resets_renewal_state(db_session):
    _put(db_session, "confluence_token_renewal", json.dumps({"id": 5}))
    try:
        put = _client(db_session).put("/api/v1/settings/confluence", json={"api_token": "manual"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert token_renewal.load_state(db_session, "confluence") == {}


def test_saving_only_address_keeps_renewal_state(db_session):
    _put(db_session, "jira_token_renewal", json.dumps({"id": 5}))
    try:
        _client(db_session).put("/api/v1/settings/jira", json={"base_url": "jira.example.test"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert token_renewal.load_state(db_session, "jira") == {"id": 5}
