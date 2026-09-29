"""Изменения сотрудников и групп публикуют entity_changed «employees» —
иначе другие вкладки и пользователи видят старые группы и плашку «Без группы»
до перезагрузки страницы."""
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam, Team, TeamSubgroup
from app.services.event_bus import get_event_bus

TEAM = "Команда"


def _client(db):
    bus = AsyncMock()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_event_bus] = lambda: bus
    return TestClient(app), bus


def _seed(db):
    db.add(Team(id="t-1", name=TEAM, has_subgroups=True))
    db.flush()
    db.add(TeamSubgroup(id="sg-1", team_id="t-1", name="Группа", sort_order=1))
    db.add(Employee(id="e-1", jira_account_id="acc-e1", display_name="Иванов",
                    role="dev", is_active=True))
    db.add(EmployeeTeam(employee_id="e-1", team=TEAM, is_primary=True))
    db.commit()


def _published(bus) -> list[list[str]]:
    return [c.args[0]["entities"] for c in bus.publish.await_args_list]


def test_deactivation_publishes_employees(db_session):
    _seed(db_session)
    client, bus = _client(db_session)
    try:
        r = client.patch("/api/v1/employees/e-1", json={"is_active": False})
        assert r.status_code == 200, r.text
        assert _published(bus) == [["employees"]]
    finally:
        app.dependency_overrides.clear()


def test_group_transfer_publishes_employees(db_session):
    _seed(db_session)
    client, bus = _client(db_session)
    try:
        r = client.put(
            "/api/v1/teams/employees/e-1/subgroup-shares",
            json={"team": TEAM, "valid_from": None,
                  "shares": [{"subgroup_id": "sg-1", "percent": 100}]},
        )
        assert r.status_code == 200, r.text
        assert _published(bus) == [["employees"]]
    finally:
        app.dependency_overrides.clear()


def test_reads_and_failures_do_not_publish(db_session):
    _seed(db_session)
    client, bus = _client(db_session)
    try:
        assert client.get("/api/v1/employees").status_code == 200
        assert client.get("/api/v1/teams/registry").status_code == 200
        assert client.patch("/api/v1/employees/nope", json={"is_active": False}).status_code == 404
        assert _published(bus) == []
    finally:
        app.dependency_overrides.clear()
