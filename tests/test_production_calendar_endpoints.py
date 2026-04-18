from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import ProductionCalendarDay


@pytest.fixture
def db_session():
    """Isolated session bound via StaticPool so Starlette worker threads
    share the same in-memory DB connection as the test thread.

    The default conftest engine uses SingletonThreadPool which gives each
    thread its own (empty) :memory: DB — that breaks post-commit refresh in
    endpoints when FastAPI dispatches sync handlers into a threadpool.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_list_year_returns_sorted(db_session):
    db_session.add_all([
        ProductionCalendarDay(date=date(2026, 5, 9), is_workday=False,
                              kind="holiday", source="xmlcalendar"),
        ProductionCalendarDay(date=date(2026, 1, 1), is_workday=False,
                              kind="holiday", source="xmlcalendar"),
    ])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.get("/api/v1/production-calendar", params={"year": 2026})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    dates = [row["date"] for row in resp.json()]
    assert dates == ["2026-01-01", "2026-05-09"]


def test_upsert_manual(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.put(
            "/api/v1/production-calendar",
            json={"date": "2026-12-31", "is_workday": False,
                  "kind": "holiday", "note": "NY eve"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "manual"
    assert body["note"] == "NY eve"


def test_delete_rejects_non_manual(db_session):
    db_session.add(ProductionCalendarDay(
        date=date(2026, 5, 9), is_workday=False, kind="holiday",
        source="xmlcalendar",
    ))
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        client = TestClient(app)
        resp = client.delete("/api/v1/production-calendar/2026-05-09")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 400


def test_sync_year_calls_service(db_session):
    from app.services.production_calendar_service import SyncStats
    with patch(
        "app.services.production_calendar_service.ProductionCalendarService.sync_year",
        new=AsyncMock(return_value=SyncStats(inserted=10, updated=0, skipped_manual=1)),
    ):
        app.dependency_overrides[get_db] = lambda: db_session
        try:
            client = TestClient(app)
            resp = client.post(
                "/api/v1/production-calendar/sync", params={"year": 2026}
            )
        finally:
            app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"inserted": 10, "updated": 0, "skipped_manual": 1}
