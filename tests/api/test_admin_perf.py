"""Раздел «Быстродействие»: доступ, чтение за период, выгрузки."""
import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models.perf import PerfMinute, PerfServerSnapshot, PerfSlowRequest
from app.models.user import User, UserRole


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed(db):
    now = datetime.utcnow()
    db.add(PerfMinute(minute=now.replace(second=0, microsecond=0) - timedelta(minutes=2),
                      method="GET", route="/api/v1/backlog/{item_id}", count=3, total_ms=7000,
                      max_ms=5000, db_count=6, db_ms=4000, h0=1, h6=1, h7=1))
    db.add(PerfSlowRequest(
        at=now - timedelta(minutes=2), method="GET", route="/api/v1/backlog/{item_id}",
        path="/api/v1/backlog/1", query="team=A", status_code=200, duration_ms=5000,
        db_count=4, db_ms=4000, cpu_ms=100, user_id=None,
        top_queries=[{"ms": 3900.0, "sql": "SELECT * FROM backlog_items WHERE id = ?"}],
    ))
    db.add(PerfServerSnapshot(
        at=now - timedelta(minutes=1), host_cpu_percent=40, host_memory_percent=50,
        process_cpu_percent=30, process_memory_mb=300, cpu_count=4, threads=20,
        db_pool_in_use=1, db_pool_size=40, requests_in_flight=2,
    ))
    db.commit()


@pytest.mark.no_auth_bypass
def test_only_admin(testclient_db_session):
    db = testclient_db_session
    app.dependency_overrides[get_db] = lambda: db
    try:
        for role, expected in ((UserRole.manager, 403), (UserRole.admin, 200)):
            email = f"perf_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
            db.add(User(id=str(uuid.uuid4()), email=email, password_hash=hash_password("pass123"),
                        display_name="Perf", role=role))
            db.commit()
            c = TestClient(app)
            token = c.post("/api/v1/auth/login",
                           json={"email": email, "password": "pass123"}).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            for path in ("/overview", "/report.md", "/export.xlsx"):
                resp = c.get(f"/api/v1/admin/perf{path}", headers=headers)
                assert resp.status_code == expected, (path, resp.text)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_overview(client, testclient_db_session):
    _seed(testclient_db_session)
    resp = client.get("/api/v1/admin/perf/overview", params={"period": "1h"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["period"] == "1h"
    assert data["bottlenecks"][0]["section"] == "Целевые задачи"
    assert data["slow"][0]["verdict"] == "database"
    assert data["totals"]["requests"] == 3
    assert data["slow_ms"] == 2000


def test_overview_rejects_unknown_period(client):
    assert client.get("/api/v1/admin/perf/overview", params={"period": "2h"}).status_code == 422


def test_report_md_download(client, testclient_db_session):
    _seed(testclient_db_session)
    resp = client.get("/api/v1/admin/perf/report.md", params={"period": "24h", "tz_offset_min": 180})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/markdown")
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment;") and ".md" in disposition
    assert disposition.isascii()
    assert "# Быстродействие сервиса" in resp.content.decode("utf-8")


def test_xlsx_download(client, testclient_db_session):
    _seed(testclient_db_session)
    resp = client.get("/api/v1/admin/perf/export.xlsx", params={"period": "7d"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert resp.headers["content-disposition"].isascii()
    assert resp.content[:2] == b"PK"


def test_report_rejects_bad_tz(client):
    resp = client.get("/api/v1/admin/perf/report.md", params={"tz_offset_min": 5000})
    assert resp.status_code == 422
