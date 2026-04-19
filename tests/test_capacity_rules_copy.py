"""Тесты копирования правил обязательных работ в следующий квартал."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.models import MonthlyCapacityRule
from app.services.capacity_service import CapacityService, RulesConflict


@pytest.fixture
def static_db():
    """StaticPool session so Starlette worker threads share the same :memory: DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(static_db):
    app.dependency_overrides[get_db] = lambda: static_db
    try:
        yield TestClient(app), static_db
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def q1_rules(db_session):
    """Q1 rules seeded into the conftest shared db_session (for service-only tests)."""
    rows = [
        MonthlyCapacityRule(id=f"r{i}", year=2026, month=m, percent_of_norm=10.0 + i)
        for i, m in enumerate([1, 2, 3])
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


@pytest.fixture
def q1_rules_static(static_db):
    """Q1 rules seeded into the StaticPool session (for endpoint tests)."""
    rows = [
        MonthlyCapacityRule(id=f"r{i}", year=2026, month=m, percent_of_norm=10.0 + i)
        for i, m in enumerate([1, 2, 3])
    ]
    static_db.add_all(rows)
    static_db.commit()
    return rows


def test_service_copies_rules(db_session, q1_rules):
    svc = CapacityService(db_session)
    created = svc.copy_rules_to_quarter(2026, 1, 2026, 2)
    assert created == 3
    months = {r.month: r.percent_of_norm for r in db_session.query(MonthlyCapacityRule).filter_by(year=2026).all()}
    assert months == {1: 10.0, 2: 11.0, 3: 12.0, 4: 10.0, 5: 11.0, 6: 12.0}


def test_service_rollover_q4_to_next_year_q1(db_session):
    rows = [
        MonthlyCapacityRule(id=f"r{i}", year=2026, month=m, percent_of_norm=5.0)
        for i, m in enumerate([10, 11, 12])
    ]
    db_session.add_all(rows)
    db_session.commit()
    svc = CapacityService(db_session)
    created = svc.copy_rules_to_quarter(2026, 4, 2027, 1)
    assert created == 3
    by_ym = {(r.year, r.month): r.percent_of_norm for r in db_session.query(MonthlyCapacityRule).all()}
    assert by_ym[(2027, 1)] == 5.0
    assert by_ym[(2027, 3)] == 5.0


def test_service_raises_on_conflict(db_session, q1_rules):
    db_session.add(MonthlyCapacityRule(id="rx", year=2026, month=5, percent_of_norm=1.0))
    db_session.commit()
    svc = CapacityService(db_session)
    with pytest.raises(RulesConflict) as exc:
        svc.copy_rules_to_quarter(2026, 1, 2026, 2)
    assert (2026, 5) in exc.value.conflicts


def test_service_raises_when_source_empty(db_session):
    svc = CapacityService(db_session)
    with pytest.raises(ValueError):
        svc.copy_rules_to_quarter(2025, 1, 2026, 2)


def test_endpoint_happy_path(client, q1_rules_static):
    tc, _ = client
    r = tc.post(
        "/api/v1/capacity/rules/copy-to-quarter",
        json={"from_year": 2026, "from_quarter": 1, "to_year": 2026, "to_quarter": 2},
    )
    assert r.status_code == 201, r.text
    assert r.json()["created"] == 3


def test_endpoint_409_on_conflict(client, q1_rules_static, static_db):
    tc, _ = client
    static_db.add(MonthlyCapacityRule(id="rx", year=2026, month=5, percent_of_norm=1.0))
    static_db.commit()
    r = tc.post(
        "/api/v1/capacity/rules/copy-to-quarter",
        json={"from_year": 2026, "from_quarter": 1, "to_year": 2026, "to_quarter": 2},
    )
    assert r.status_code == 409
    assert [2026, 5] in r.json()["detail"]["conflicts"]
