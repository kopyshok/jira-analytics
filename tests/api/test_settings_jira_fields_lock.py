"""Поля Jira, пока переезд на новую Jira не завершён, настраиваются только на странице переезда."""
import pytest
from fastapi.testclient import TestClient

from app.api.endpoints.settings import FIELDS_LOCKED_MESSAGE
from app.database import get_db
from app.main import app
from app.models.app_setting import AppSetting
from app.services.jira_migration.state import STATE_DONE, STATE_PENDING, set_migration_state

URL = "/api/v1/settings/generic"
PLANNED_DEV = '[{"field_id":"customfield_2","kind":"alt","name":"Разработка (ч)"}]'


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _migration(db, state):
    set_migration_state(db, state)
    db.commit()


@pytest.mark.parametrize("key, value", [
    ("jira_team_field_id", "customfield_1"),
    ("jira_planned_dev_hours_field_id", PLANNED_DEV),
    ("jira_sprint_field_id", ""),
])
def test_field_setting_locked_while_migration_pending(client, db_session, key, value):
    _migration(db_session, STATE_PENDING)
    db_session.add(AppSetting(key=key, value="customfield_old"))
    db_session.commit()

    resp = client.put(URL, json={"key": key, "value": value})

    assert resp.status_code == 409
    assert resp.json()["detail"] == FIELDS_LOCKED_MESSAGE
    db_session.expire_all()
    assert db_session.query(AppSetting).filter_by(key=key).one().value == "customfield_old"


def test_field_setting_readable_while_migration_pending(client, db_session):
    _migration(db_session, STATE_PENDING)
    db_session.add(AppSetting(key="jira_team_field_id", value="customfield_old"))
    db_session.commit()

    resp = client.get(f"{URL}/jira_team_field_id")

    assert resp.status_code == 200
    assert resp.json()["value"] == "customfield_old"


def test_other_settings_saved_while_migration_pending(client, db_session):
    _migration(db_session, STATE_PENDING)

    assert client.put(URL, json={"key": "ui_team_projects", "value": "OS"}).status_code == 200


def test_field_setting_saved_after_migration(client, db_session):
    _migration(db_session, STATE_DONE)

    resp = client.put(URL, json={"key": "jira_team_field_id", "value": "customfield_1"})

    assert resp.status_code == 200
    assert db_session.query(AppSetting).filter_by(key="jira_team_field_id").one().value == "customfield_1"
