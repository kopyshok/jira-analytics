"""Страница «Переезд на новую Jira»: доступ, запуск прогона, решения, применение."""
import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.core.security import hash_password
from app.database import get_db
from app.main import app
from app.models import Employee, Issue
from app.models.jira_migration import JiraMigrationReport
from app.models.user import User, UserRole
from app.repositories.sync_run import SyncRunRepository
from app.api.endpoints.jira_migration import POST_CHECK_BUSY
from app.services.jira_migration import overview, resolution, runner, store
from app.services.jira_migration.resolution import BLOCK_DONE, BLOCK_JOB
from app.services.jira_migration.state import STATE_DONE, STATE_PENDING, set_migration_state
from app.services.sync_lock import SyncLock
from tests.services.jira_migration.factory import make_worklog
from tests.services.jira_migration.fake_jira import FakeJira, dc_user
from tests.services.jira_migration.ready import seed_ready

BASE = "/api/v1/admin/jira-migration"
SUMMARY = {
    "settings": 3, "issues_deleted": 2, "choices_dropped": 1, "worklogs_deleted": 10,
    "worklogs_kept": 2, "comments_deleted": 4, "comments_kept": 1, "kpi_payload_skipped": 0,
}


@pytest.fixture(autouse=True)
def fresh_job():
    runner._job = runner.MigrationJob()
    yield
    runner._job = runner.MigrationJob()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def ready(db_session):
    return seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))


def _pending(db):
    set_migration_state(db, STATE_PENDING)
    db.commit()


def _mark_applied(db, ids, *, sync_run_id=None):
    """Как после применения: «переезд завершён», итог и запуск синхронизации — в отчёте."""
    set_migration_state(db, STATE_DONE)
    row = db.get(JiraMigrationReport, ids["report"])
    row.applied_at = datetime.utcnow()
    row.apply_summary_json = json.dumps(SUMMARY)
    row.sync_run_id = sync_run_id
    db.commit()


@contextmanager
def _no_resolve():
    """Пересчёт решений по базе запрещён (и в ответе страницы, и в препятствиях)."""
    boom = AssertionError("resolve() не должен вызываться")
    with patch.object(overview, "resolve", side_effect=boom), patch.object(resolution, "resolve", side_effect=boom):
        yield


@pytest.mark.no_auth_bypass
def test_only_admin(testclient_db_session):
    for role, expected in ((UserRole.manager, 403), (UserRole.admin, 200)):
        email = f"jm_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
        testclient_db_session.add(User(
            id=str(uuid.uuid4()), email=email, password_hash=hash_password("pass123"),
            display_name="Проверка доступа", role=role,
        ))
        testclient_db_session.commit()
        app.dependency_overrides[get_db] = lambda: testclient_db_session
        try:
            http = TestClient(app)
            login = http.post("/api/v1/auth/login", json={"email": email, "password": "pass123"})
            token = login.json()["access_token"]
            assert http.get(BASE, headers={"Authorization": f"Bearer {token}"}).status_code == expected
        finally:
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.no_auth_bypass
def test_every_endpoint_needs_admin(testclient_db_session):
    email = f"jm_mgr_{uuid.uuid4().hex[:8]}@example.com"
    testclient_db_session.add(User(
        id=str(uuid.uuid4()), email=email, password_hash=hash_password("pass123"),
        display_name="Проверка доступа", role=UserRole.manager,
    ))
    testclient_db_session.commit()
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        http = TestClient(app)
        token = http.post("/api/v1/auth/login", json={"email": email, "password": "pass123"}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        calls = [
            http.post(f"{BASE}/dry-run", headers=headers),
            http.put(f"{BASE}/decisions", headers=headers,
                     json={"kind": "issue", "item_key": "OS-2", "decision": None}),
            http.get(f"{BASE}/dc-users", headers=headers, params={"q": "Петров"}),
            http.post(f"{BASE}/apply", headers=headers, json={"backup_confirmed": True}),
            http.post(f"{BASE}/full-sync", headers=headers),
            http.post(f"{BASE}/post-check", headers=headers),
        ]
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert [r.status_code for r in calls] == [403] * 6


@pytest.mark.no_auth_bypass
def test_anonymous_gets_401(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    try:
        assert TestClient(app).get(BASE).status_code == 401
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_overview_without_report(client, db_session):
    _pending(db_session)

    body = client.get(BASE).json()

    assert body["migration_state"] == "pending"
    assert body["report"] is None
    assert body["blockers"] == ["Пробный прогон ещё не запускался"]
    assert body["backup_command"] == "docker compose exec postgres-backup /backup.sh"
    assert body["job"]["state"] == "idle"


def test_dry_run_started_once(client, db_session):
    _pending(db_session)
    with patch.object(runner, "start_dry_run", MagicMock()) as start:
        first = client.post(f"{BASE}/dry-run")
        second = client.post(f"{BASE}/dry-run")

    assert first.status_code == 202
    assert first.json()["state"] == "running"
    assert first.json()["kind"] == "dry_run"
    assert second.status_code == 409
    start.assert_called_once_with(runner.current_job())


def test_dry_run_refused_after_migration(client, db_session):
    set_migration_state(db_session, STATE_DONE)
    db_session.commit()
    with patch.object(runner, "start_dry_run", MagicMock()) as start:
        assert client.post(f"{BASE}/dry-run").status_code == 409
    start.assert_not_called()


def test_person_decision_roundtrip(client, ready):
    resp = client.put(f"{BASE}/decisions", json={
        "kind": "person", "item_key": ready["sidorov"],
        "decision": {"action": "bind", "key": "JIRAUSER8", "name": "Sidorov_S", "display_name": "Сидоров Сидор"},
    })
    assert resp.status_code == 200

    body = client.get(BASE).json()
    people = {p["employee_id"]: p for p in body["report"]["people"]}
    assert people[ready["sidorov"]]["final"]["key"] == "JIRAUSER8"
    assert [i["key"] for i in body["report"]["issues"]["missing_with_data"]] == ["OS-2", "OS-3"]
    assert body["unresolved"] == {"fields": 0, "issues": 0, "people": 0}
    assert body["blockers"] == []
    assert 0.9 <= body["report"]["age_hours"] <= 1.1

    client.put(f"{BASE}/decisions", json={"kind": "person", "item_key": ready["sidorov"], "decision": None})
    people = {p["employee_id"]: p for p in client.get(BASE).json()["report"]["people"]}
    assert people[ready["sidorov"]]["final"]["unresolved"] is True


def test_overview_passes_report_warnings(client, db_session, ready):
    """Сдвиг времени, проекты без пары в новой Jira и сбрасываемые выборы оценки — на страницу."""
    row = db_session.get(JiraMigrationReport, ready["report"])
    data = store.report_data(row)
    data["offset_unexpected"] = True
    data["issues"]["project_not_found"] = [{"key": "OLD", "issues": 4}]
    row.report_json = json.dumps(data, ensure_ascii=False)
    db_session.commit()
    resolution = overview.resolve(db_session, row)

    report = client.get(BASE).json()["report"]

    assert report["offset_unexpected"] is True
    assert report["issues"]["project_not_found"] == [{"key": "OLD", "issues": 4}]
    assert report["choices_dropped"] == resolution.choices_dropped


def test_overview_counts_issues_and_hours_to_delete(client, db_session, ready):
    """Сколько задач удалит применение (сами и по решению) и сколько часов списаний уйдёт с ними."""
    ivanov = db_session.get(Employee, ready["ivanov"])
    for key, seconds in (("OS-1", 1800), ("OS-2", 5400), ("OS-3", 3600)):
        issue = db_session.query(Issue).filter_by(key=key).one()
        make_worklog(db_session, issue, ivanov, datetime(2026, 9, 11, 10, 0), seconds, f"w-{key}")
    db_session.commit()

    issues = client.get(BASE).json()["report"]["issues"]

    assert issues["deletable_total"] == 1
    assert (issues["to_delete_total"], issues["to_delete_hours"]) == (2, 2.0)


def test_bad_decisions_rejected(client, ready):
    bad_shape = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-2", "decision": {"action": "archive"},
    })
    present_in_dc = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-91030", "decision": {"action": "delete"},
    })
    unknown_field = client.put(f"{BASE}/decisions", json={
        "kind": "field", "item_key": "customfield_11526", "decision": {"dc_field_id": "customfield_404"},
    })
    assert (bad_shape.status_code, present_in_dc.status_code, unknown_field.status_code) == (422, 422, 422)


def test_malformed_decision_values_rejected(client, ready):
    """Значение не той формы — 422 ещё до сверки с отчётом, а не падение сервера."""
    resp = client.put(f"{BASE}/decisions", json={
        "kind": "field", "item_key": "customfield_11526", "decision": {"dc_field_id": ["x"]},
    })
    assert resp.status_code == 422


def test_issue_decision_classifies_only_that_issue(client, db_session, ready):
    with patch.object(overview, "classify_missing", wraps=overview.classify_missing) as classify:
        resp = client.put(f"{BASE}/decisions", json={
            "kind": "issue", "item_key": "OS-3", "decision": {"action": "delete"},
        })
        not_missing = client.put(f"{BASE}/decisions", json={
            "kind": "issue", "item_key": "OS-91030", "decision": {"action": "delete"},
        })

    assert (resp.status_code, not_missing.status_code) == (200, 422)
    assert [call.args[1] for call in classify.call_args_list] == [["OS-3"]]


def test_decisions_locked_while_operation_runs(client, db_session, ready):
    runner.claim(db_session, runner.KIND_DRY_RUN)
    resp = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-3", "decision": {"action": "delete"},
    })
    assert resp.status_code == 409


def test_decisions_locked_after_migration(client, db_session, ready):
    _mark_applied(db_session, ready)
    resp = client.put(f"{BASE}/decisions", json={
        "kind": "issue", "item_key": "OS-3", "decision": {"action": "delete"},
    })
    assert resp.status_code == 409


def test_apply_needs_backup_tick(client, ready):
    with patch.object(runner, "start_apply", MagicMock()) as start:
        resp = client.post(f"{BASE}/apply", json={"backup_confirmed": False})
    assert resp.status_code == 409
    assert "копия базы" in resp.json()["detail"]
    start.assert_not_called()


def test_apply_starts_job(client, ready):
    with patch.object(runner, "start_apply", MagicMock()) as start:
        resp = client.post(f"{BASE}/apply", json={"backup_confirmed": True})
        again = client.post(f"{BASE}/apply", json={"backup_confirmed": True})

    assert resp.status_code == 202
    assert (resp.json()["kind"], resp.json()["state"]) == ("apply", "running")
    assert again.status_code == 409
    start.assert_called_once()
    assert start.call_args.args == (runner.current_job(),)
    assert start.call_args.kwargs == {"backup_confirmed": True}


def test_overview_skips_resolution_while_apply_runs(client, db_session, ready):
    """Пока идёт применение, сопоставления по базе не пересчитываются: только ход операции."""
    runner.claim(db_session, runner.KIND_APPLY)
    runner.current_job().step = runner.STEP_APPLY

    with _no_resolve():
        body = client.get(BASE).json()

    assert body["job"]["kind"] == "apply"
    assert body["job"]["step"] == runner.STEP_APPLY
    assert body["blockers"] == [BLOCK_JOB]
    assert body["report"]["status"] == "done"
    assert "people" not in body["report"]


def test_overview_after_apply_shows_stored_summary(client, db_session, ready):
    """После применения отчёт не пересчитывается по базе: итог применения и сверка — из отчёта."""
    _mark_applied(db_session, ready)
    store.save_post_check(db_session, ready["report"], {"checked_at": "x", "rows": []})

    with _no_resolve():
        body = client.get(BASE).json()

    assert body["migration_state"] == "done"
    assert body["apply_summary"] == SUMMARY
    assert body["applied_at"] is not None
    assert body["post_check"] == {"checked_at": "x", "rows": []}
    assert body["blockers"] == [BLOCK_DONE]
    assert body["unresolved"] == {"fields": 0, "issues": 0, "people": 0}
    report = body["report"]
    assert report["status"] == "done"
    assert report["hours"]["rows"][0]["team"] == "Команда А"
    assert report["offset_unexpected"] is False
    assert not {"fields", "issues", "people"} & set(report)


def test_running_report_without_job_is_interrupted_at_once(client, db_session):
    """Сервис — один процесс: отчёт «идёт», а прогона в процессе нет — прерван, без ожидания."""
    _pending(db_session)
    store.start_report(db_session, datetime.utcnow() - timedelta(minutes=1))

    body = client.get(BASE).json()

    assert body["report"]["status"] == "failed"
    assert body["report"]["error"] == runner.RUN_INTERRUPTED
    assert body["blockers"] == [resolution.BLOCK_FAILED]


def test_running_report_with_dry_run_in_process(client, db_session):
    _pending(db_session)
    runner.claim(db_session, runner.KIND_DRY_RUN)
    store.start_report(db_session, datetime.utcnow())

    body = client.get(BASE).json()

    assert body["report"]["status"] == "running"
    assert body["report"]["error"] is None
    assert body["blockers"] == [BLOCK_JOB]


def test_running_report_old_is_interrupted(client, db_session):
    _pending(db_session)
    store.start_report(db_session, datetime.utcnow() - timedelta(hours=3))

    body = client.get(BASE).json()

    assert body["report"]["status"] == "failed"
    assert body["report"]["error"] == runner.RUN_INTERRUPTED


def test_running_sync_run_without_job_is_interrupted(client, db_session, ready):
    """Запуск «идёт», а полной синхронизации в процессе нет — прервана сразу, даже под своей блокировкой."""
    run_id = SyncRunRepository(db_session).create(mode="full", trigger="manual").id
    _mark_applied(db_session, ready, sync_run_id=run_id)

    free = client.get(BASE).json()["sync_run"]
    SyncLock(db_session).acquire(run_id)
    held = client.get(BASE).json()["sync_run"]
    runner.claim(db_session, runner.KIND_FULL_SYNC)
    live = client.get(BASE).json()["sync_run"]

    assert (free["id"], free["status"], free["error"]) == (run_id, "interrupted", runner.SYNC_INTERRUPTED)
    assert (held["status"], held["error"]) == ("interrupted", runner.SYNC_INTERRUPTED)
    assert (live["status"], live["error"]) == ("running", None)


def test_sync_run_raw_error_shown_as_generic_text(client, db_session, ready):
    """Сырой текст исключения из истории запусков на страницу не попадает; известные тексты — как есть."""
    repo = SyncRunRepository(db_session)
    raw = repo.create(mode="full", trigger="manual").id
    repo.finalize(raw, status="failed", stages=[], error_text="'NoneType' object has no attribute 'id'")
    _mark_applied(db_session, ready, sync_run_id=raw)
    shown_raw = client.get(BASE).json()["sync_run"]["error"]
    lost = repo.create(mode="full", trigger="manual").id
    repo.finalize(lost, status="failed", stages=[], error_text=runner.LOCK_LOST)
    store.set_sync_run(db_session, ready["report"], lost)
    shown_lost = client.get(BASE).json()["sync_run"]["error"]

    assert (shown_raw, shown_lost) == (runner.FULL_SYNC_ERROR, runner.LOCK_LOST)


def _assert_poll_skips_maps(client, db_session):
    """Опрос страницы: ни один запрос к базе не читает соответствия отчёта (мегабайты)."""
    db_session.expire_all()  # иначе уже загруженная строка отчёта не дала бы запроса вовсе
    seen: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        assert client.get(BASE).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert any("jira_migration_reports" in s for s in seen)
    assert not [s for s in seen if "maps_json" in s]


def test_overview_never_loads_report_maps(client, db_session, ready):
    _assert_poll_skips_maps(client, db_session)  # до применения: решения по базе
    runner.claim(db_session, runner.KIND_APPLY)
    _assert_poll_skips_maps(client, db_session)  # идёт применение
    runner._job = runner.MigrationJob()
    run_id = SyncRunRepository(db_session).create(mode="full", trigger="manual").id
    _mark_applied(db_session, ready, sync_run_id=run_id)
    _assert_poll_skips_maps(client, db_session)  # после применения


def test_overview_never_loads_report_maps_while_dry_run_runs(client, db_session):
    _pending(db_session)
    runner.claim(db_session, runner.KIND_DRY_RUN)
    store.start_report(db_session, datetime.utcnow())

    _assert_poll_skips_maps(client, db_session)


def test_post_check_only_after_apply(client, ready):
    assert client.post(f"{BASE}/post-check").status_code == 409


def test_post_check_after_apply(client, db_session, ready):
    _mark_applied(db_session, ready)

    resp = client.post(f"{BASE}/post-check")

    assert resp.status_code == 200
    assert resp.json()["rows"][0]["team"] == "Команда А"
    assert client.get(BASE).json()["post_check"] == resp.json()


def test_post_check_refused_while_operation_runs(client, db_session, ready):
    _mark_applied(db_session, ready)
    runner.claim(db_session, runner.KIND_FULL_SYNC)

    resp = client.post(f"{BASE}/post-check")

    assert resp.status_code == 409
    assert resp.json()["detail"] == POST_CHECK_BUSY
    assert client.get(BASE).json()["post_check"] is None


def test_full_sync_restart_only_after_apply(client, ready):
    with patch.object(runner, "start_full_sync_restart", MagicMock()) as start:
        assert client.post(f"{BASE}/full-sync").status_code == 409
    start.assert_not_called()


def test_full_sync_restart_claims_slot(client, db_session, ready):
    _mark_applied(db_session, ready)
    with patch.object(runner, "start_full_sync_restart", MagicMock()) as start:
        first = client.post(f"{BASE}/full-sync")
        second = client.post(f"{BASE}/full-sync")

    assert first.status_code == 202
    assert (first.json()["kind"], first.json()["state"]) == ("full_sync", "running")
    assert second.status_code == 409
    start.assert_called_once_with(runner.current_job())


def test_full_sync_restart_refused_while_other_sync_runs(client, db_session, ready):
    _mark_applied(db_session, ready)
    SyncLock(db_session).acquire("other-run")
    with patch.object(runner, "start_full_sync_restart", MagicMock()) as start:
        resp = client.post(f"{BASE}/full-sync")

    assert resp.status_code == 409
    assert resp.json()["detail"] == runner.SYNC_BUSY
    assert runner.current_job().state == runner.JOB_IDLE
    start.assert_not_called()


def test_full_sync_restart_after_crash_takes_dead_lock(client, db_session, ready):
    """Блокировку держит прерванный перезапуском запуск этого переезда — повтор доступен сразу."""
    run_id = SyncRunRepository(db_session).create(mode="full", trigger="manual").id
    _mark_applied(db_session, ready, sync_run_id=run_id)
    SyncLock(db_session).acquire(run_id)
    with patch.object(runner, "start_full_sync_restart", MagicMock()) as start:
        resp = client.post(f"{BASE}/full-sync")

    assert resp.status_code == 202
    start.assert_called_once_with(runner.current_job())


def test_full_sync_restart_after_crash_waits_for_other_sync(client, db_session, ready):
    run_id = SyncRunRepository(db_session).create(mode="full", trigger="manual").id
    _mark_applied(db_session, ready, sync_run_id=run_id)
    SyncLock(db_session).acquire("other-run")
    with patch.object(runner, "start_full_sync_restart", MagicMock()) as start:
        resp = client.post(f"{BASE}/full-sync")

    assert resp.status_code == 409
    assert resp.json()["detail"] == runner.SYNC_BUSY
    start.assert_not_called()


def test_dc_user_search(client, db_session):
    fake = FakeJira(users=[
        dc_user("JIRAUSER7", "Petrov_P", "Петров Пётр"),
        dc_user("JIRAUSER9", "Petrov_A", "Петров Антон", active=False),
    ])
    with patch("app.api.endpoints.jira_migration.JiraClient.from_db", return_value=fake):
        resp = client.get(f"{BASE}/dc-users", params={"q": "Петров"})

    assert resp.status_code == 200
    assert resp.json() == [
        {"key": "JIRAUSER7", "name": "Petrov_P", "display_name": "Петров Пётр", "email": None, "active": True},
        {"key": "JIRAUSER9", "name": "Petrov_A", "display_name": "Петров Антон", "email": None, "active": False},
    ]


def test_dc_user_search_releases_database_and_does_not_retry(client, db_session):
    """Пока ждём Jira, соединение с базой не занято; интерактивный поиск — без повторов."""
    seen: dict = {}

    class Recording(FakeJira):
        async def search_users(self, *args, **kwargs):
            seen["in_transaction"] = db_session.in_transaction()
            seen["max_retries"] = getattr(self, "max_retries", None)
            return await super().search_users(*args, **kwargs)

    db_session.query(User).first()  # сессия держит соединение, как после чтения настроек
    with patch("app.api.endpoints.jira_migration.JiraClient.from_db", return_value=Recording()):
        resp = client.get(f"{BASE}/dc-users", params={"q": "Петров"})

    assert resp.status_code == 200
    assert seen == {"in_transaction": False, "max_retries": 1}


def test_dc_user_search_jira_unavailable(client, db_session):
    fake = FakeJira(fail={"search_users"})
    with patch("app.api.endpoints.jira_migration.JiraClient.from_db", return_value=fake):
        resp = client.get(f"{BASE}/dc-users", params={"q": "Петров"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == runner.JIRA_UNAVAILABLE
