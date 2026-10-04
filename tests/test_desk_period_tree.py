"""Поток 6: выбор квартала на публичном столе и полное дерево «Мои задачи»."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    ResourcePlan,
    ResourcePlanAssignment,
    Worklog,
)
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
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
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
def emp(db_session):
    e = Employee(
        id="emp-desk-1", jira_account_id="acc-desk-1", display_name="Стол Аналитик",
        is_active=True, role="analyst", team="Alpha", synced_at=datetime.utcnow(),
    )
    db_session.add(e)
    db_session.add(EmployeeTeam(id="et-1", employee_id=e.id, team="Alpha", is_primary=True))
    db_session.commit()
    return e


def _cur() -> tuple[int, int]:
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


def _shift(delta: int) -> tuple[int, int]:
    year, quarter = _cur()
    idx = year * 4 + quarter - 1 + delta
    return idx // 4, idx % 4 + 1


def _desk(db_session, emp, widgets=None):
    return WorkDeskService().create(db_session, emp.id, widgets or list(WIDGET_KEYS), "usr-1")


# ── endpoint: year/quarter ──────────────────────────────────────────────────


def test_meta_period_param_respected(client, db_session, emp):
    desk = _desk(db_session, emp, ["hours_balance"])
    year, quarter = _shift(-2)
    r = client.get(f"/api/v1/desk/{desk.token}", params={"year": year, "quarter": quarter})
    assert r.status_code == 200
    assert r.json()["period"] == {"year": year, "quarter": quarter}


def test_meta_default_is_current(client, db_session, emp):
    desk = _desk(db_session, emp, [])
    year, quarter = _cur()
    assert client.get(f"/api/v1/desk/{desk.token}").json()["period"] == {
        "year": year, "quarter": quarter,
    }


def test_widget_period_param_respected(client, db_session, emp):
    desk = _desk(db_session, emp, ["team_absences"])
    year, quarter = _shift(1)
    r = client.get(
        f"/api/v1/desk/{desk.token}/widget/team_absences",
        params={"year": year, "quarter": quarter},
    )
    assert r.status_code == 200
    assert (r.json()["year"], r.json()["quarter"]) == (year, quarter)


@pytest.mark.parametrize("delta", [-4, 4])
def test_period_limit_inclusive(client, db_session, emp, delta):
    desk = _desk(db_session, emp, [])
    year, quarter = _shift(delta)
    r = client.get(f"/api/v1/desk/{desk.token}", params={"year": year, "quarter": quarter})
    assert r.status_code == 200


@pytest.mark.parametrize("delta", [-5, 5])
def test_period_beyond_limit_422(client, db_session, emp, delta):
    desk = _desk(db_session, emp, ["team_absences"])
    year, quarter = _shift(delta)
    params = {"year": year, "quarter": quarter}
    assert client.get(f"/api/v1/desk/{desk.token}", params=params).status_code == 422
    r = client.get(f"/api/v1/desk/{desk.token}/widget/team_absences", params=params)
    assert r.status_code == 422


def test_period_invalid_values_422(client, db_session, emp):
    desk = _desk(db_session, emp, [])
    url = f"/api/v1/desk/{desk.token}"
    year, quarter = _cur()
    assert client.get(url, params={"year": year, "quarter": 5}).status_code == 422
    assert client.get(url, params={"year": year, "quarter": 0}).status_code == 422
    assert client.get(url, params={"year": "abc", "quarter": 1}).status_code == 422
    # Одно без другого — неоднозначно.
    assert client.get(url, params={"year": year}).status_code == 422
    assert client.get(url, params={"quarter": quarter}).status_code == 422


# ── дерево «Мои задачи» ─────────────────────────────────────────────────────


def _issue(iid, key, parent=None, status="In Progress", cat="indeterminate", **kw):
    return Issue(
        id=iid, jira_issue_id=f"ji-{iid}", key=key, summary=f"Задача {key}",
        issue_type="Sub-task" if parent else "Задача", status=status,
        status_category=cat, project_id="prj-1", parent_id=parent,
        participating_teams="[]", **kw,
    )


def _seed_tree(db_session, emp_id):
    """Инициатива P → A → A1 → A11; P → B; P → C (закрыта)."""
    year, quarter = _cur()
    month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    db_session.add(Project(id="prj-1", jira_project_id="10000", key="ITL", name="ITL", is_active=True))
    db_session.add_all([
        _issue("iss-P", "ITL-1"),
        _issue("iss-A", "ITL-2", "iss-P", assignee_display_name="Иван", estimated_hours=10.0),
        _issue("iss-A1", "ITL-3", "iss-A"),
        _issue("iss-A11", "ITL-4", "iss-A1", estimated_hours=4.0),
        _issue("iss-B", "ITL-5", "iss-P", estimated_hours=6.0),
        _issue("iss-C", "ITL-6", "iss-P", status="Done", cat="done"),
    ])
    db_session.add(BacklogItem(id="bi-1", title="Инициатива A", issue_id="iss-P"))
    db_session.add(ResourcePlan(
        id="plan-1", team="Alpha", year=year, quarter=str(quarter),
        status="ready", computed_at=datetime.utcnow(),
    ))
    db_session.add(ResourcePlanAssignment(
        id="rpa-1", plan_id="plan-1", backlog_item_id="bi-1",
        phase="analyst", employee_id=emp_id, hours_allocated=10.0,
    ))
    for i, (iid, h) in enumerate([("iss-A11", 3.0), ("iss-A", 1.0), ("iss-B", 2.0)]):
        db_session.add(Worklog(
            id=f"wl-{i}", jira_worklog_id=f"jwl-{i}", issue_id=iid,
            employee_id=emp_id, started_at=datetime(year, month, 15, 10),
            time_spent_seconds=int(h * 3600), hours=h,
        ))
    db_session.commit()


def _my_tasks(db_session, desk, period=None):
    year, quarter = period or _cur()
    return dispatch(db_session, desk, "my_tasks", year, quarter)


def test_full_tree_to_leaves(db_session, emp):
    _seed_tree(db_session, emp.id)
    top = _my_tasks(db_session, _desk(db_session, emp))["projects"][0]["children"]
    by_key = {c["key"]: c for c in top}
    assert set(by_key) == {"ITL-2", "ITL-5", "ITL-6"}
    a = by_key["ITL-2"]
    assert a["fact_hours"] == 4.0  # поддерево A: 1 + 3
    assert a["estimate_hours"] == 10.0
    assert a["assignee"] == "Иван"
    assert a["jira_url"].endswith("ITL-2")
    a1 = a["children"][0]
    assert a1["key"] == "ITL-3" and a1["fact_hours"] == 3.0
    assert a1["estimate_hours"] == 4.0  # своей оценки нет — сумма детей
    leaf = a1["children"][0]
    assert leaf["key"] == "ITL-4" and leaf["children"] == []
    assert leaf["fact_hours"] == 3.0
    assert by_key["ITL-6"]["status_category"] == "done"
    assert by_key["ITL-6"]["estimate_hours"] is None


def test_tree_survives_cycle(db_session, emp):
    _seed_tree(db_session, emp.id)
    db_session.get(Issue, "iss-A").parent_id = "iss-A11"
    db_session.commit()
    out = _my_tasks(db_session, _desk(db_session, emp))
    assert out["projects"][0]["key"] == "ITL-1"


def test_tree_query_count_independent_of_node_count(db_session, emp):
    _seed_tree(db_session, emp.id)
    for n in range(40):
        db_session.add(_issue(f"iss-x{n}", f"ITL-9{n}", "iss-B"))
    db_session.commit()
    desk = _desk(db_session, emp)
    stmts: list[str] = []
    engine = db_session.get_bind()

    def _count(conn, cursor, statement, *a):
        stmts.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        _my_tasks(db_session, desk)
    finally:
        event.remove(engine, "before_cursor_execute", _count)
    assert len(stmts) < 40


def test_my_tasks_follows_selected_quarter(db_session, emp):
    _seed_tree(db_session, emp.id)
    assert _my_tasks(db_session, _desk(db_session, emp), _shift(-1))["projects"] == []


def test_production_calendar_month_counter_only_in_current_quarter(db_session, emp):
    desk = _desk(db_session, emp)
    prev = dispatch(db_session, desk, "production_calendar", *_shift(-1))
    assert prev["month_workdays"] == 0 and prev["month_work_hours"] == 0.0
    cur = dispatch(db_session, desk, "production_calendar", *_cur())
    assert cur["quarter_workdays"] > 0
