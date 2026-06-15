"""Управление рабочими столами (/work-desks) — CRUD + скоупинг по командам пользователя."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam, User, UserRole
from app.services.work_desk_service import WorkDeskService


def _seed_manager(db: Session, teams: list[str]) -> User:
    u = User(
        id="usr-mgr",
        email=f"{uuid.uuid4()}@test",
        password_hash="x",
        display_name="Manager",
        role=UserRole.manager,
        is_active=True,
    )
    u.selected_teams = teams
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _seed_employee(db: Session, team: str) -> Employee:
    emp = Employee(
        id=str(uuid.uuid4()),
        jira_account_id=str(uuid.uuid4()),
        display_name=f"Emp {team}",
        is_active=True,
    )
    db.add(emp)
    db.flush()
    db.add(EmployeeTeam(employee_id=emp.id, team=team, is_primary=True))
    db.commit()
    db.refresh(emp)
    return emp


@pytest.fixture
def db_session_tc(testclient_db_session: Session) -> Session:
    return testclient_db_session


@pytest.fixture
def manager(db_session_tc: Session) -> User:
    return _seed_manager(db_session_tc, ["TeamA"])


@pytest.fixture
def emp_in_team_a(db_session_tc: Session) -> Employee:
    return _seed_employee(db_session_tc, "TeamA")


@pytest.fixture
def emp_in_team_b(db_session_tc: Session) -> Employee:
    return _seed_employee(db_session_tc, "TeamB")


@pytest.fixture
def client_as_manager(db_session_tc: Session, manager: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db_session_tc
    app.dependency_overrides[get_current_user] = lambda: manager
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def test_create_desk_for_own_team(client_as_manager, db_session_tc, emp_in_team_a):
    r = client_as_manager.post(
        "/api/v1/work-desks",
        json={"employee_id": emp_in_team_a.id, "enabled_widgets": ["hours_balance"]},
    )
    assert r.status_code == 201
    assert r.json()["token"]


def test_create_desk_foreign_employee_403(client_as_manager, db_session_tc, emp_in_team_b):
    r = client_as_manager.post(
        "/api/v1/work-desks",
        json={"employee_id": emp_in_team_b.id, "enabled_widgets": []},
    )
    assert r.status_code == 403


def test_regenerate_kills_old_link(client_as_manager, db_session_tc, emp_in_team_a):
    created = client_as_manager.post(
        "/api/v1/work-desks",
        json={"employee_id": emp_in_team_a.id, "enabled_widgets": []},
    ).json()
    old = created["token"]
    desk_id = created["id"]
    client_as_manager.post(f"/api/v1/work-desks/{desk_id}/regenerate")
    assert client_as_manager.get(f"/api/v1/desk/{old}").status_code == 404


def test_list_returns_scoped_desks(client_as_manager, db_session_tc, emp_in_team_a, emp_in_team_b):
    svc = WorkDeskService()
    svc.create(db_session_tc, emp_in_team_a.id, [], "usr-mgr")
    svc.create(db_session_tc, emp_in_team_b.id, [], "usr-other")
    r = client_as_manager.get("/api/v1/work-desks")
    ids = [d["employee"]["id"] for d in r.json()]
    assert emp_in_team_a.id in ids
    assert emp_in_team_b.id not in ids


def test_patch_widgets_own_team(client_as_manager, db_session_tc, emp_in_team_a):
    created = client_as_manager.post(
        "/api/v1/work-desks",
        json={"employee_id": emp_in_team_a.id, "enabled_widgets": []},
    ).json()
    r = client_as_manager.patch(
        f"/api/v1/work-desks/{created['id']}",
        json={"enabled_widgets": ["hours_balance", "absences"]},
    )
    assert r.status_code == 200
    assert r.json()["enabled_widgets"] == ["hours_balance", "absences"]


def test_patch_foreign_desk_403(client_as_manager, db_session_tc, emp_in_team_b):
    desk = WorkDeskService().create(db_session_tc, emp_in_team_b.id, [], "usr-other")
    r = client_as_manager.patch(
        f"/api/v1/work-desks/{desk.id}", json={"enabled_widgets": []}
    )
    assert r.status_code == 403


def test_patch_missing_desk_404(client_as_manager, db_session_tc):
    r = client_as_manager.patch(
        "/api/v1/work-desks/does-not-exist", json={"enabled_widgets": []}
    )
    assert r.status_code == 404


def test_revoke_own_team(client_as_manager, db_session_tc, emp_in_team_a):
    created = client_as_manager.post(
        "/api/v1/work-desks",
        json={"employee_id": emp_in_team_a.id, "enabled_widgets": []},
    ).json()
    token = created["token"]
    r = client_as_manager.post(f"/api/v1/work-desks/{created['id']}/revoke")
    assert r.status_code == 200
    assert client_as_manager.get(f"/api/v1/desk/{token}").status_code == 404


def test_revoke_foreign_desk_403(client_as_manager, db_session_tc, emp_in_team_b):
    desk = WorkDeskService().create(db_session_tc, emp_in_team_b.id, [], "usr-other")
    r = client_as_manager.post(f"/api/v1/work-desks/{desk.id}/revoke")
    assert r.status_code == 403


def test_revoke_missing_404(client_as_manager, db_session_tc):
    r = client_as_manager.post("/api/v1/work-desks/nope/revoke")
    assert r.status_code == 404


def test_regenerate_foreign_403(client_as_manager, db_session_tc, emp_in_team_b):
    desk = WorkDeskService().create(db_session_tc, emp_in_team_b.id, [], "usr-other")
    r = client_as_manager.post(f"/api/v1/work-desks/{desk.id}/regenerate")
    assert r.status_code == 403
