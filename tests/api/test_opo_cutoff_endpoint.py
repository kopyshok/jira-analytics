"""Отсечку ОПЭ читает любой пользователь, не только администратор."""

import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth_deps import get_current_user, require_admin
from app.database import get_db
from app.main import app
from app.models import AppSetting, User, UserRole


def test_non_admin_reads_opo_cutoff(testclient_db_session):
    db = testclient_db_session
    manager = User(
        id=str(uuid.uuid4()), email=f"{uuid.uuid4()}@test", password_hash="x",
        display_name="Руководитель", role=UserRole.manager, is_active=True,
    )
    db.add(manager)
    db.add(AppSetting(key="planning_opo_cutoff", value="2026Q4"))
    db.commit()

    def _require_admin_impl():
        raise HTTPException(status_code=403, detail="Только для администратора")

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: manager
    app.dependency_overrides[require_admin] = _require_admin_impl
    try:
        client = TestClient(app)
        assert client.get("/api/v1/settings/generic/planning_opo_cutoff").status_code == 403
        resp = client.get("/api/v1/planning/opo-cutoff")
        assert resp.status_code == 200
        assert resp.json()["value"] == "2026Q4"
    finally:
        app.dependency_overrides.clear()
        db.query(AppSetting).filter(AppSetting.key == "planning_opo_cutoff").delete()
        db.delete(manager)
        db.commit()
