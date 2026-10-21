"""Даты вкладки «Синхронизация → Дополнительно» читает любой пользователь.

Раздел синхронизации открыт всем, а ``/settings`` — только администратору:
читать даты оттуда значило получать отказ у всех, кроме администратора,
а дату перечитывания задач — отказ и у него.
"""

import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.main import app
from app.models import AppSetting, User, UserRole

URL = "/api/v1/sync/reload-dates"


def test_reload_dates_empty_until_first_run(testclient_db_session):
    db = testclient_db_session
    app.dependency_overrides[get_db] = lambda: db
    try:
        resp = TestClient(app).get(URL)
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert resp.status_code == 200
    assert resp.json() == {"worklogs_since": None, "issues_since": None}


def test_non_admin_reads_reload_dates(testclient_db_session):
    db = testclient_db_session
    manager = User(
        id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@test", password_hash="x",
        display_name="Руководитель", role=UserRole.manager, is_active=True,
    )
    db.add(manager)
    db.add(AppSetting(key="worklog_reload_since_date", value="2026-03-01"))
    db.add(AppSetting(key="issues_reload_since_date", value="2026-04-15"))
    db.commit()

    def _require_admin_impl():
        raise HTTPException(status_code=403, detail="Только для администратора")

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: manager
    app.dependency_overrides[require_admin] = _require_admin_impl
    try:
        resp = TestClient(app).get(URL)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json() == {"worklogs_since": "2026-03-01", "issues_since": "2026-04-15"}
