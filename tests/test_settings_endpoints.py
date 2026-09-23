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


def test_generic_settings_keep_plan_hours_field_list(client: TestClient):
    """Настройка роли — JSON-список полей: сохраняется и читается как есть."""
    import json

    from app.services.plan_sources import FieldSpec, parse_field_setting

    value = json.dumps([
        {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
        {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"},
    ], ensure_ascii=False)
    r = client.put(
        "/api/v1/settings/generic",
        json={"key": "jira_planned_dev_hours_field_id", "value": value},
    )
    assert r.status_code == 200, r.text

    got = client.get("/api/v1/settings/generic/jira_planned_dev_hours_field_id").json()["value"]
    assert got == value
    assert parse_field_setting(got) == (
        FieldSpec("customfield_12432", "alt", "Разработка (ч)"),
        FieldSpec("customfield_12888", "sum", "Оценка Back"),
    )


PLAN_KEY = "jira_planned_dev_hours_field_id"


def _put_plan_fields(client: TestClient, value):
    return client.put("/api/v1/settings/generic", json={"key": PLAN_KEY, "value": value})


def _seed_cursors(db) -> None:
    from datetime import datetime

    from app.models import SyncState

    stamp = datetime(2026, 9, 1, 12, 0)
    db.add_all([
        SyncState(entity_name="issues", scope="", last_success_at=stamp),
        SyncState(entity_name="issues", scope="Team X", last_success_at=stamp),
        SyncState(entity_name="worklogs", scope="", last_success_at=stamp),
    ])
    db.commit()


def _cursors(db) -> dict:
    from app.models import SyncState

    db.expire_all()
    return {(s.entity_name, s.scope): s.last_success_at for s in db.query(SyncState).all()}


@pytest.mark.parametrize("value", [
    "[]", "[{", '[{"id": "customfield_12432"}]', '[{"field_id": ""}]', ' ["customfield_12432"]',
])
def test_plan_hours_unreadable_list_is_422(client: TestClient, db_session, value):
    """Значение-список, из которого не читается ни одного поля, не сохраняется:
    синк молча перестал бы брать оценку роли."""
    db_session.add(AppSetting(key=PLAN_KEY, value="customfield_12432"))
    db_session.commit()

    assert _put_plan_fields(client, value).status_code == 422
    db_session.expire_all()
    assert db_session.query(AppSetting).filter_by(key=PLAN_KEY).one().value == "customfield_12432"


def test_plan_hours_fields_change_resets_issue_sync_cursors(client: TestClient, db_session):
    """Новые поля оценки: следующий синк перечитывает все задачи, а не только
    изменённые в Jira, — иначе у старых задач не появятся значения новых полей."""
    import json

    db_session.add(AppSetting(key=PLAN_KEY, value="customfield_12432"))
    _seed_cursors(db_session)

    value = json.dumps([
        {"field_id": "customfield_12432", "kind": "alt"},
        {"field_id": "customfield_14648", "kind": "alt"},
    ])
    assert _put_plan_fields(client, value).status_code == 200

    cursors = _cursors(db_session)
    assert cursors[("issues", "")] is None
    assert cursors[("issues", "Team X")] is None
    assert cursors[("worklogs", "")] is not None


@pytest.mark.parametrize("value", [
    "customfield_12432", " customfield_12432 ", '[{"field_id": "customfield_12432", "kind": "alt"}]',
])
def test_plan_hours_same_fields_keep_cursors(client: TestClient, db_session, value):
    """Те же поля в другой записи (старая строка → список) — перечитывать нечего."""
    db_session.add(AppSetting(key=PLAN_KEY, value="customfield_12432"))
    _seed_cursors(db_session)

    assert _put_plan_fields(client, value).status_code == 200

    assert _cursors(db_session)[("issues", "")] is not None


@pytest.mark.parametrize("stored, value", [
    # Старая строка → тот же список с названием: редактор подписал поле.
    (
        "customfield_12432",
        '[{"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"}]',
    ),
    # Поменялись только названия.
    (
        '[{"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},'
        ' {"field_id": "customfield_12888", "kind": "sum"}]',
        '[{"field_id": "customfield_12432", "kind": "alt"},'
        ' {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"}]',
    ),
])
def test_plan_hours_names_only_keep_cursors(client: TestClient, db_session, stored, value):
    """Название поля — только подпись варианта в споре: синк читает те же поля,
    перечитывать все задачи незачем."""
    db_session.add(AppSetting(key=PLAN_KEY, value=stored))
    _seed_cursors(db_session)

    assert _put_plan_fields(client, value).status_code == 200

    assert _cursors(db_session)[("issues", "")] is not None


@pytest.mark.parametrize("stored, value", [
    # Другой вид поля.
    (
        "customfield_12432",
        '[{"field_id": "customfield_12432", "kind": "sum", "name": "Разработка (ч)"}]',
    ),
    # Другой порядок: до выбора действует верхнее поле.
    (
        '[{"field_id": "customfield_12432", "kind": "alt"}, {"field_id": "customfield_14648", "kind": "alt"}]',
        '[{"field_id": "customfield_14648", "kind": "alt"}, {"field_id": "customfield_12432", "kind": "alt"}]',
    ),
])
def test_plan_hours_kind_or_order_change_resets_cursors(client: TestClient, db_session, stored, value):
    db_session.add(AppSetting(key=PLAN_KEY, value=stored))
    _seed_cursors(db_session)

    assert _put_plan_fields(client, value).status_code == 200

    assert _cursors(db_session)[("issues", "")] is None


def test_other_field_setting_keeps_cursors(client: TestClient, db_session):
    _seed_cursors(db_session)
    r = client.put(
        "/api/v1/settings/generic",
        json={"key": "jira_team_field_id", "value": "customfield_11526"},
    )
    assert r.status_code == 200
    assert _cursors(db_session)[("issues", "")] is not None
