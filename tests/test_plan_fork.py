"""Тесты plan fork — клонирование плана со всеми назначениями."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import ResourcePlan, ResourcePlanAssignment


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
        app.dependency_overrides.pop(get_db, None)


def test_fork_creates_new_plan_with_cloned_assignments(client, db_session):
    plan = ResourcePlan(
        team="T", quarter="Q2", year=2026, status="ready", is_baseline=True
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)

    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id="BI-1",
        phase="dev",
        employee_id="EMP-1",
        part_number=1,
        hours_allocated=10.0,
    )
    db_session.add(a)
    db_session.commit()

    r = client.post(
        f"/api/v1/resource-planning/resource-plans/{plan.id}/fork",
        json={"label": "Что если +1 разработчик"},
    )
    assert r.status_code == 201
    new = r.json()
    assert new["parent_plan_id"] == plan.id
    assert new["is_baseline"] is False
    assert new["label"] == "Что если +1 разработчик"

    cloned = (
        db_session.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == new["id"]
            )
        )
        .scalars()
        .all()
    )
    assert len(cloned) == 1
    assert cloned[0].backlog_item_id == "BI-1"


def test_fork_unknown_plan_returns_404(client):
    r = client.post(
        "/api/v1/resource-planning/resource-plans/no-such-id/fork",
        json={"label": "test"},
    )
    assert r.status_code == 404


def test_diff_endpoint_returns_metrics(client, db_session):
    from datetime import date

    base = ResourcePlan(
        team="T", quarter="Q2", year=2026, status="ready", is_baseline=True
    )
    scen = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db_session.add_all([base, scen])
    db_session.commit()
    db_session.refresh(base)
    db_session.refresh(scen)

    db_session.add(
        ResourcePlanAssignment(
            plan_id=base.id,
            backlog_item_id="BI-1",
            phase="dev",
            part_number=1,
            hours_allocated=10.0,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
        )
    )
    db_session.add(
        ResourcePlanAssignment(
            plan_id=scen.id,
            backlog_item_id="BI-1",
            phase="dev",
            part_number=1,
            hours_allocated=10.0,
            start_date=date(2026, 4, 8),
            end_date=date(2026, 4, 12),
        )
    )
    db_session.commit()

    r = client.get(f"/api/v1/resource-planning/resource-plans/{scen.id}/diff/{base.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["baseline_id"] == base.id
    assert body["scenario_id"] == scen.id
    assert len(body["assignment_shifts"]) == 1
    assert body["assignment_shifts"][0]["start_delta_days"] == 7


def test_diff_endpoint_404_for_unknown(client):
    r = client.get("/api/v1/resource-planning/resource-plans/no-scen/diff/no-base")
    assert r.status_code == 404
