"""ui_config endpoint — hidden_sections GET/PUT."""
import json

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting


def _make_client(testclient_db_session):
    def _override():
        try:
            yield testclient_db_session
        finally:
            pass
    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_get_returns_empty_when_no_setting(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.get("/api/v1/ui-config/hidden-sections")
        assert r.status_code == 200, r.text
        assert r.json() == {"keys": []}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_returns_existing_keys(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        testclient_db_session.add(AppSetting(
            key="ui_hidden_section_keys",
            value=json.dumps(["/executive", "/projects"]),
        ))
        testclient_db_session.commit()
        r = client.get("/api/v1/ui-config/hidden-sections")
        assert r.status_code == 200
        assert sorted(r.json()["keys"]) == ["/executive", "/projects"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_put_dedupes_and_sorts_keys(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        r = client.put(
            "/api/v1/ui-config/hidden-sections",
            json={"keys": ["/executive", "/executive", " /backlog ", ""]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["keys"] == ["/backlog", "/executive"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_get_after_put_persists(testclient_db_session):
    client = _make_client(testclient_db_session)
    try:
        client.put(
            "/api/v1/ui-config/hidden-sections",
            json={"keys": ["/executive"]},
        )
        r = client.get("/api/v1/ui-config/hidden-sections")
        assert r.json()["keys"] == ["/executive"]
    finally:
        app.dependency_overrides.pop(get_db, None)
