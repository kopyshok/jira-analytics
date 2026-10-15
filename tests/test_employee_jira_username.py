"""Логин Jira DC у сотрудника: пишется синком, по нему ищутся списания (ведро B)."""
from datetime import datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.connectors.schemas import JiraUserSchema
from app.database import get_db
from app.main import app
from app.models import Employee, EmployeeTeam
from app.services.sync_service import SyncService, UpdateStats


def test_upsert_stores_and_refreshes_login(db_session):
    svc = SyncService(db_session, MagicMock())
    svc._ensure_employee(JiraUserSchema(key="JIRAUSER1", name="Ivanov_I_I", displayName="Иванов"))
    db_session.commit()
    svc._ensure_employee(JiraUserSchema(key="JIRAUSER1", name="Ivanov_I", displayName="Иванов"))
    db_session.commit()

    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER1").one()
    assert emp.jira_username == "Ivanov_I"


def test_user_without_login_keeps_stored_login(db_session):
    db_session.add(Employee(jira_account_id="JIRAUSER3", jira_username="kept",
                            display_name="Анна", is_active=True))
    db_session.commit()
    svc = SyncService(db_session, MagicMock())
    svc._ensure_employee(JiraUserSchema(key="JIRAUSER3", displayName="Анна"))
    db_session.commit()
    assert db_session.query(Employee).filter_by(jira_account_id="JIRAUSER3").one().jira_username == "kept"


def test_cached_employee_gets_renamed_login(db_session):
    emp = Employee(jira_account_id="JIRAUSER2", jira_username="old_login",
                   display_name="Пётр", is_active=True)
    db_session.add(emp)
    db_session.commit()
    svc = SyncService(db_session, MagicMock())
    cache = {emp.jira_account_id: emp}

    svc._ensure_employee_cached(
        JiraUserSchema(key="JIRAUSER2", name="new_login", displayName="Пётр"), cache,
    )
    db_session.commit()
    assert db_session.get(Employee, emp.id).jira_username == "new_login"


async def test_bucket_b_queries_by_login_and_skips_unbound(db_session):
    db_session.add_all([
        Employee(id="e-1", jira_account_id="JIRAUSER1", jira_username="Ivanov_I_I",
                 display_name="Иванов", is_active=True, synced_at=datetime.utcnow()),
        Employee(id="e-2", jira_account_id="cloud:abc", display_name="Без привязки",
                 is_active=True, synced_at=datetime.utcnow()),
    ])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(id="et-1", employee_id="e-1", team="Alpha", is_primary=True),
        EmployeeTeam(id="et-2", employee_id="e-2", team="Alpha", is_primary=True),
    ])
    db_session.commit()

    jqls: list[str] = []
    lenient_flags: list[bool] = []

    async def fake_iter_issues(jql, fields=None, max_results=100, lenient=False):
        jqls.append(jql)
        lenient_flags.append(lenient)
        if False:
            yield

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    svc = SyncService(db_session, jira)
    await svc._update_worklogs_bucket_b("2026-02-01", ["Alpha"], UpdateStats())

    assert jqls == ['worklogAuthor = "Ivanov_I_I" AND updated >= "2026-02-01"']
    # Исчезнувший в Jira логин — предупреждение, а не остановка обновления для всех.
    assert lenient_flags == [True]


def test_employee_from_jira_stores_login(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).post("/api/v1/employees/from-jira", json={
            "jira_account_id": "JIRAUSER7",
            "jira_username": "Petrov_P_P",
            "display_name": "Петров Пётр",
            "email": None,
            "is_active": True,
            "avatar_url": None,
        })
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER7").one()
    assert emp.jira_username == "Petrov_P_P"


async def test_bucket_b_escapes_quote_and_backslash_in_login(db_session):
    db_session.add_all([
        Employee(id="e-q", jira_account_id="JIRAUSER11", jira_username='o"neil',
                 display_name="Кавычка", is_active=True, synced_at=datetime.utcnow()),
        Employee(id="e-b", jira_account_id="JIRAUSER12", jira_username="dom\\user",
                 display_name="Слэш", is_active=True, synced_at=datetime.utcnow()),
    ])
    db_session.flush()
    db_session.add_all([
        EmployeeTeam(id="et-q", employee_id="e-q", team="Alpha", is_primary=True),
        EmployeeTeam(id="et-b", employee_id="e-b", team="Alpha", is_primary=True),
    ])
    db_session.commit()

    jqls: list[str] = []

    async def fake_iter_issues(jql, fields=None, max_results=100, lenient=False):
        jqls.append(jql)
        if False:
            yield

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    await SyncService(db_session, jira)._update_worklogs_bucket_b(
        "2026-02-01", ["Alpha"], UpdateStats(),
    )

    assert sorted(jqls) == sorted([
        'worklogAuthor = "o\\"neil" AND updated >= "2026-02-01"',
        'worklogAuthor = "dom\\\\user" AND updated >= "2026-02-01"',
    ])


def test_team_clause_escapes_team_name():
    assert SyncService._team_jql_clause("customfield_11526", 'A"\\B') == 'cf[11526] = "A\\"\\\\B"'


def test_employee_from_jira_update_without_login_keeps_login(db_session):
    db_session.add(Employee(jira_account_id="JIRAUSER8", jira_username="Sidorov_S_S",
                            display_name="Сидоров", is_active=True))
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        resp = TestClient(app).post("/api/v1/employees/from-jira", json={
            "jira_account_id": "JIRAUSER8",
            "display_name": "Сидоров Сергей",
        })
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert resp.status_code == 200
    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER8").one()
    assert emp.display_name == "Сидоров Сергей"
    assert emp.jira_username == "Sidorov_S_S"


def test_deleted_jira_user_keeps_employee_name_and_login(db_session):
    """Удалённый в Jira автор (без имени) не затирает ФИО и логин сотрудника."""
    from app.services.sync_service import _author_as_user

    db_session.add(Employee(jira_account_id="JIRAUSER14008", jira_username="Ivanov_I_I",
                            display_name="Иванов Иван", is_active=False))
    db_session.commit()
    author = JiraUserSchema.model_validate({"name": "JIRAUSER14008", "active": False})
    svc = SyncService(db_session, MagicMock())
    svc._ensure_employee(_author_as_user(author))
    svc._ensure_employee_cached(author, {})
    db_session.commit()

    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER14008").one()
    assert emp.display_name == "Иванов Иван"
    assert emp.jira_username == "Ivanov_I_I"


def test_deleted_jira_user_unknown_creates_employee_by_key(db_session):
    author = JiraUserSchema.model_validate({"name": "JIRAUSER14009", "active": False})
    SyncService(db_session, MagicMock())._ensure_employee(author)
    db_session.commit()

    emp = db_session.query(Employee).filter_by(jira_account_id="JIRAUSER14009").one()
    assert emp.display_name == "JIRAUSER14009"
    assert emp.jira_username is None
