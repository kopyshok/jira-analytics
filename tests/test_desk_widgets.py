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
from app.models import Comment, Employee, EmployeeTeam, Issue, Project
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


# ── dispatcher + enabled-gate ───────────────────────────────────────────────


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
    assert len(WIDGET_KEYS) == 8
    assert set(WIDGET_KEYS) == {
        "my_tasks",
        "my_timeline",
        "hours_balance",
        "category_breakdown",
        "team_absences",
        "team_availability",
        "production_calendar",
        "awaiting_reaction",
    }


# ── adapters: contract shape on sparse seed ─────────────────────────────────


def _make_desk(db_session, emp_id):
    return WorkDeskService().create(db_session, emp_id, list(WIDGET_KEYS), "usr-1")


def _dispatch(db_session, desk, key):
    year, quarter = _current_quarter()
    return dispatch(db_session, desk, key, year, quarter)


def test_my_tasks_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    assert isinstance(out["projects"], list)
    assert out["projects"] == []


def test_my_timeline_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_timeline")
    assert "quarter_start" in out
    assert "quarter_end" in out
    assert isinstance(out["bars"], list)
    assert out["bars"] == []


def test_hours_balance_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "hours_balance")
    assert isinstance(out["balance_hours"], float)
    assert isinstance(out["days"], list)


def test_category_breakdown_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "category_breakdown")
    assert isinstance(out["work_types"], list)
    assert out["work_types"] == []


def test_team_absences_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_absences")
    assert isinstance(out["employees"], list)
    assert isinstance(out["absences"], list)
    assert isinstance(out["year"], int)
    assert isinstance(out["quarter"], int)
    # Сотрудник стола состоит в команде Alpha — строка-сотрудник должна быть.
    assert any(e["id"] == seed_employee.id for e in out["employees"])
    assert out["absences"] == []


def test_team_availability_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_availability")
    assert isinstance(out["members"], list)
    assert out["members"] == []


def test_production_calendar_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "production_calendar")
    assert isinstance(out["quarter_workdays"], int)
    assert isinstance(out["month_workdays"], int)
    assert isinstance(out["days"], list)
    assert out["quarter_workdays"] > 0  # квартал всегда содержит рабочие дни
    # дни покрывают весь квартал
    assert len(out["days"]) >= 89
    for d in out["days"][:1]:
        assert {"date", "kind", "hours"} <= set(d)


def test_awaiting_reaction_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "awaiting_reaction")
    assert isinstance(out["items"], list)
    assert out["items"] == []


def test_awaiting_reaction_with_comment(db_session, seed_employee):
    """Задача назначена сотруднику, не завершена, последний коммент — от другого."""
    other = Employee(
        id="emp-other",
        jira_account_id="acc-other",
        display_name="Коллега",
        is_active=True,
        synced_at=datetime.utcnow(),
    )
    proj = Project(
        id="proj-1",
        jira_project_id="10000",
        key="ALP",
        name="Alpha Project",
        synced_at=datetime.utcnow(),
    )
    db_session.add_all([other, proj])
    issue = Issue(
        id="iss-1",
        jira_issue_id="20000",
        key="ALP-1",
        summary="Нужен ответ",
        issue_type="Task",
        status="In Progress",
        status_category="indeterminate",
        project_id=proj.id,
        assignee_display_name="Стол Аналитик",
    )
    db_session.add(issue)
    db_session.add(
        Comment(
            id="cmt-1",
            jira_comment_id="c-1",
            body="Что по задаче?",
            jira_created_at=datetime(2026, 6, 10, 12, 0, 0),
            issue_id=issue.id,
            author_id=other.id,
            synced_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    desk = _make_desk(db_session, seed_employee.id)
    year, quarter = _current_quarter()
    out = dispatch(db_session, desk, "awaiting_reaction", year, quarter)
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["key"] == "ALP-1"
    assert item["title"] == "Нужен ответ"
    assert item["last_comment_author"] == "Коллега"
    assert item["last_comment_at"] is not None


def test_awaiting_reaction_excludes_own_last_comment(db_session, seed_employee):
    """Если последний коммент написал сам сотрудник — мяч не на его стороне."""
    proj = Project(
        id="proj-2",
        jira_project_id="10001",
        key="ALP2",
        name="Alpha Project 2",
        synced_at=datetime.utcnow(),
    )
    db_session.add(proj)
    issue = Issue(
        id="iss-2",
        jira_issue_id="20001",
        key="ALP-2",
        summary="Я ответил",
        issue_type="Task",
        status="In Progress",
        status_category="indeterminate",
        project_id=proj.id,
        assignee_display_name="Стол Аналитик",
    )
    db_session.add(issue)
    db_session.add(
        Comment(
            id="cmt-2",
            jira_comment_id="c-2",
            body="Ответил",
            jira_created_at=datetime(2026, 6, 11, 9, 0, 0),
            issue_id=issue.id,
            author_id=seed_employee.id,
            synced_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    desk = _make_desk(db_session, seed_employee.id)
    year, quarter = _current_quarter()
    out = dispatch(db_session, desk, "awaiting_reaction", year, quarter)
    assert out["items"] == []
