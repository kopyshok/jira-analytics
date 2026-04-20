"""API tests for /planning endpoints (currently: /capacity-preview)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Category,
    Employee,
    MandatoryWorkType,
    ProductionCalendarDay,
    RoleCapacityRule,
)


# Local db_session that uses StaticPool so the FastAPI TestClient (which
# hits app dependency_overrides on a separate thread/connection) sees the
# same in-memory schema created above.
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
def productive_setup(db_session):
    """100% productive fallback rule on Q2 2026 so available_hours > 0."""
    wt = MandatoryWorkType(
        code="productive", label="Продуктив", is_active=True
    )
    db_session.add(wt)
    db_session.flush()
    db_session.add(
        Category(
            code="cat_productive",
            label="Productive",
            is_system=False,
            work_type_id=wt.id,
        )
    )
    db_session.add(
        RoleCapacityRule(
            year=2026,
            quarter=2,
            role=None,
            work_type_id=wt.id,
            percent_of_norm=100.0,
        )
    )
    db_session.flush()
    return wt


@pytest.fixture
def q2_calendar(db_session):
    """Seed Q2 2026 calendar: 22 workdays × 8h per month."""
    from calendar import monthrange

    for m in (4, 5, 6):
        last = monthrange(2026, m)[1]
        for d in range(1, last + 1):
            is_wd = d <= 22
            db_session.add(
                ProductionCalendarDay(
                    date=date(2026, m, d),
                    is_workday=is_wd,
                    kind="workday" if is_wd else "holiday",
                    hours=8.0 if is_wd else 0.0,
                )
            )
    db_session.commit()


@pytest.fixture
def api_client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_capacity_preview_returns_per_role_demand(
    db_session, productive_setup, q2_calendar, api_client
):
    db_session.add_all(
        [
            Employee(
                id="e1",
                display_name="A",
                jira_account_id="a1",
                is_active=True,
                role="analyst",
            ),
            Employee(
                id="e2",
                display_name="D",
                jira_account_id="a2",
                is_active=True,
                role="dev",
            ),
            Employee(
                id="e3",
                display_name="Q",
                jira_account_id="a3",
                is_active=True,
                role="qa",
            ),
        ]
    )
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                priority=1,
                estimate_analyst_hours=40,
                estimate_dev_hours=80,
                estimate_qa_hours=20,
                estimate_opo_hours=0,
                estimate_hours=140,
            ),
        ]
    )
    db_session.commit()

    r = api_client.post(
        "/api/v1/planning/capacity-preview",
        json={"year": 2026, "quarter": 2, "backlog_item_ids": ["b1"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["demand_by_role"]["analyst"] == 40
    assert body["demand_by_role"]["dev"] == 80
    assert body["demand_by_role"]["qa"] == 20
    assert body["capacity_by_role"]["analyst"] > 0
    assert body["capacity_by_role"]["dev"] > 0
    assert body["capacity_by_role"]["qa"] > 0
    assert len(body["per_employee"]) == 3
    # Totals should match per-role sums.
    assert body["total_demand"] == pytest.approx(140.0)
    assert body["total_capacity"] == pytest.approx(
        sum(body["capacity_by_role"].values())
    )


def test_capacity_preview_splits_opo_between_analyst_and_dev(
    db_session, productive_setup, q2_calendar, api_client
):
    db_session.add_all(
        [
            Employee(
                id="e1",
                display_name="A",
                jira_account_id="a1",
                is_active=True,
                role="analyst",
            ),
            Employee(
                id="e2",
                display_name="D",
                jira_account_id="a2",
                is_active=True,
                role="dev",
            ),
        ]
    )
    db_session.add_all(
        [
            BacklogItem(
                id="b1",
                title="T1",
                priority=1,
                estimate_analyst_hours=10,
                estimate_dev_hours=10,
                estimate_qa_hours=0,
                estimate_opo_hours=100,
                opo_analyst_ratio=0.7,
                estimate_hours=120,
            ),
        ]
    )
    db_session.commit()

    r = api_client.post(
        "/api/v1/planning/capacity-preview",
        json={"year": 2026, "quarter": 2, "backlog_item_ids": ["b1"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # analyst = 10 + 100 * 0.7 = 80
    # dev     = 10 + 100 * 0.3 = 40
    assert body["demand_by_role"]["analyst"] == pytest.approx(80.0)
    assert body["demand_by_role"]["dev"] == pytest.approx(40.0)
    assert body["demand_by_role"]["qa"] == 0


def test_capacity_preview_with_team_filter(
    db_session, productive_setup, q2_calendar, api_client
):
    from app.models import EmployeeTeam

    db_session.add_all(
        [
            Employee(
                id="e1",
                display_name="Alpha-A",
                jira_account_id="a1",
                is_active=True,
                role="analyst",
            ),
            Employee(
                id="e2",
                display_name="Beta-A",
                jira_account_id="a2",
                is_active=True,
                role="analyst",
            ),
            EmployeeTeam(
                id="t1", employee_id="e1", team="Alpha", is_primary=True
            ),
            EmployeeTeam(
                id="t2", employee_id="e2", team="Beta", is_primary=True
            ),
        ]
    )
    db_session.commit()

    r = api_client.post(
        "/api/v1/planning/capacity-preview",
        json={
            "year": 2026,
            "quarter": 2,
            "backlog_item_ids": [],
            "team_filter": ["Alpha"],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["per_employee"]) == 1
    assert body["per_employee"][0]["employee_id"] == "e1"


def test_capacity_preview_empty_backlog_gives_zero_demand(
    db_session, productive_setup, q2_calendar, api_client
):
    db_session.add(
        Employee(
            id="e1",
            display_name="A",
            jira_account_id="a1",
            is_active=True,
            role="analyst",
        )
    )
    db_session.commit()

    r = api_client.post(
        "/api/v1/planning/capacity-preview",
        json={"year": 2026, "quarter": 2, "backlog_item_ids": []},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_demand"] == 0
    assert all(v == 0 for v in body["demand_by_role"].values())
