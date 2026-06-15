"""Тесты диспетчера и адаптеров виджетов рабочего стола.

Адаптеры проверяются на разреженном seed: контракт (топ-уровневые ключи и
типы значений) должен соблюдаться, пустые данные → пустые списки, без 500.
"""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Employee, EmployeeTeam
from app.services.work_desk_service import WorkDeskService
from app.services.work_desk_widgets import WIDGET_KEYS, dispatch


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
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def seed_employee(db_session):
    emp = Employee(
        id="emp-desk-1",
        jira_account_id="acc-desk-1",
        display_name="Стол Аналитик",
        avatar_url="https://example.com/a.png",
        is_active=True,
        role="analyst",
        team="Alpha",
        synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(id="et-1", employee_id=emp.id, team="Alpha", is_primary=True))
    db_session.commit()
    return emp


def _current_quarter() -> tuple[int, int]:
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


# ── Task 3.0: dispatcher + enabled-gate ─────────────────────────────────────


def test_widget_not_enabled_403(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    assert client.get(f"/api/v1/desk/{desk.token}/widget/my_tasks").status_code == 403


def test_widget_unknown_key_404(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["bogus"], "usr-1")
    assert client.get(f"/api/v1/desk/{desk.token}/widget/bogus").status_code == 404


def test_widget_enabled_returns_200(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    r = client.get(f"/api/v1/desk/{desk.token}/widget/hours_balance")
    assert r.status_code == 200
    assert "balance_hours" in r.json()


def test_dispatch_unknown_key_raises(db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, [], "usr-1")
    year, quarter = _current_quarter()
    with pytest.raises(ValueError):
        dispatch(db_session, desk, "nope", year, quarter)


def test_all_widget_keys_count():
    assert len(WIDGET_KEYS) == 12


# ── Tasks 3.1–3.12: adapters return correct contract shape on sparse seed ────


def _make_desk(db_session, emp_id):
    return WorkDeskService().create(db_session, emp_id, list(WIDGET_KEYS), "usr-1")


def _dispatch(db_session, desk, key):
    year, quarter = _current_quarter()
    return dispatch(db_session, desk, key, year, quarter)


def test_my_tasks_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    assert isinstance(out["tasks"], list)
    assert out["tasks"] == []


def test_weekly_load_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "weekly_load")
    assert isinstance(out["months"], list)
    assert len(out["months"]) == 3
    for m in out["months"]:
        assert {"year", "month", "norm_hours", "fact_hours"} <= set(m)


def test_my_conflicts_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_conflicts")
    assert out["conflicts"] == []


def test_hours_balance_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "hours_balance")
    assert isinstance(out["balance_hours"], float)
    assert isinstance(out["days"], list)


def test_unlogged_days_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "unlogged_days")
    assert isinstance(out["days"], list)


def test_category_breakdown_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "category_breakdown")
    assert out["categories"] == []


def test_team_absences_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_absences")
    assert out["absences"] == []


def test_team_availability_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_availability")
    assert "week_start" in out
    assert isinstance(out["members"], list)


def test_production_calendar_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "production_calendar")
    assert isinstance(out["quarter_workdays"], int)
    assert isinstance(out["remaining_workdays"], int)
    assert isinstance(out["days"], list)
    assert out["quarter_workdays"] > 0  # квартал всегда содержит рабочие дни


def test_quarter_deadlines_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "quarter_deadlines")
    assert out["items"] == []


def test_external_help_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "external_help")
    assert isinstance(out["own_hours"], float)
    assert isinstance(out["alien_hours"], float)
    assert isinstance(out["by_team"], list)


def test_recent_changes_empty_when_no_last_viewed(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    # last_viewed_at None сразу после create
    out = _dispatch(db_session, desk, "recent_changes")
    assert out["changes"] == []
