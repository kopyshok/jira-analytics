"""Настройки: состояние самопродления токенов и сброс при ручной замене."""
import json
from types import SimpleNamespace

import pytest
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


@pytest.mark.parametrize("system", ["jira", "confluence"])
@pytest.mark.parametrize("expires", [None, "2026-12-01T15:00:00+03:00"])
def test_save_manual_token_expiry(db_session, system, expires):
    try:
        put = _client(db_session).put(f"/api/v1/settings/{system}", json={
            "api_token": "manual", "token_expires_at": expires,
        })
        saved = _client(db_session).get(f"/api/v1/settings/{system}")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    expected = "2026-12-01T12:00:00+00:00" if expires else None
    assert token_renewal.load_state(db_session, system) == {"expires_at": expected}
    assert saved.json()["token_expiry_known"] is True
    assert saved.json()["token_expires_at"] == expected


@pytest.mark.parametrize("system", ["jira", "confluence"])
def test_change_expiry_without_replacing_token_keeps_owned_id(db_session, system):
    _put(db_session, f"{system}_api_token", "saved")
    _put(db_session, f"{system}_token_renewal", json.dumps({
        "id": 5, "expires_at": "2026-11-06T12:00:00+00:00",
    }))
    try:
        put = _client(db_session).put(f"/api/v1/settings/{system}", json={"token_expires_at": None})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 200
    assert token_renewal.load_state(db_session, system) == {"id": 5, "expires_at": None}
    assert db_session.query(AppSetting).filter(AppSetting.key == f"{system}_api_token").one().value == "saved"


@pytest.mark.parametrize("system", ["jira", "confluence"])
@pytest.mark.parametrize("expires", ["invalid", "2026-12-01T12:00:00"])
def test_invalid_or_timezone_missing_expiry_rejected(db_session, system, expires):
    try:
        put = _client(db_session).put(f"/api/v1/settings/{system}", json={
            "api_token": "manual", "token_expires_at": expires,
        })
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 422
    assert token_renewal.load_state(db_session, system) == {}


@pytest.mark.parametrize("system", ["jira", "confluence"])
def test_expiry_without_a_saved_token_rejected(db_session, system):
    try:
        put = _client(db_session).put(f"/api/v1/settings/{system}", json={"token_expires_at": None})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert put.status_code == 400
    assert token_renewal.load_state(db_session, system) == {}
