"""Фоновые операции переезда: прогон, применение, полная синхронизация после, сверка."""
import asyncio
import threading
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.connectors.jira_client import JiraClientError
from app.models import SyncRun
from app.models.jira_migration import JiraMigrationReport
from app.repositories.sync_run import SyncRunRepository
from app.services.jira_migration import runner, store
from app.services.jira_migration.state import (
    STATE_DONE,
    STATE_PENDING,
    get_migration_state,
    set_migration_state,
)
from app.services.sync_lock import SyncLock
from app.services.sync_pipeline import PipelineOrchestrator, Stage, WorklogsFullStage
from tests.services.jira_migration.factory import seed_report
from tests.services.jira_migration.fake_jira import FakeJira
from tests.services.jira_migration.ready import seed_ready
from tests.services.jira_migration.world import dc_world, seed_world


@pytest.fixture(autouse=True)
def fresh_job():
    runner._job = runner.MigrationJob()
    yield
    runner._job = runner.MigrationJob()


def _session(db):
    return lambda: db


class _Step(Stage):
    """Стадия-подмена: выполняет переданное действие."""

    critical = True

    def __init__(self, name, action):
        self.name = name
        self.action = action

    async def run(self, ctx):
        await self.action()
        return {}


def _done_with_report(db, applied: bool = False):
    set_migration_state(db, STATE_DONE)
    db.commit()
    report_id = seed_report(db, {"probe": []}, {}, datetime.utcnow())
    if applied:
        db.get(JiraMigrationReport, report_id).applied_at = datetime.utcnow()
        db.commit()
    return report_id


def _steal_lock(db):
    """Другой запуск забрал блокировку (наша показалась ему зависшей)."""
    SyncLock(db)._write({"run_id": "other-run", "started_at": datetime.utcnow().isoformat()})


def _broken_session():
    raise RuntimeError("no database")


# --- Занятие слота -----------------------------------------------------------

def test_claim_refuses_second_operation(db_session):
    runner.claim(db_session, runner.KIND_DRY_RUN)
    with pytest.raises(RuntimeError):
        runner.claim(db_session, runner.KIND_APPLY)


def test_claim_marks_report_without_live_run_failed_at_once(db_session):
    """Сервис — один процесс: отчёт «идёт», а прогона здесь нет — прерван перезапуском, без ожидания."""
    report_id = store.start_report(db_session, datetime.utcnow() - timedelta(minutes=1))

    job = runner.claim(db_session, runner.KIND_DRY_RUN)

    assert job.state == runner.JOB_RUNNING
    row = db_session.get(JiraMigrationReport, report_id)
    assert (row.status, row.error) == (store.STATUS_FAILED, runner.RUN_INTERRUPTED)


def test_report_in_progress_only_with_dry_run_in_this_process(db_session):
    store.start_report(db_session, datetime.utcnow())
    row = store.latest_report(db_session)

    assert runner.report_in_progress(row, runner.MigrationJob()) is False
    assert runner.report_in_progress(
        row, runner.MigrationJob(kind=runner.KIND_DRY_RUN, state=runner.JOB_RUNNING),
    ) is True
    assert runner.report_in_progress(
        row, runner.MigrationJob(kind=runner.KIND_DRY_RUN, state=runner.JOB_DONE),
    ) is False


def test_claim_marks_abandoned_report_failed(db_session):
    """Отчёт «идёт» дольше двух часов — прогон прерван, отчёт помечается неудачным."""
    report_id = store.start_report(db_session, datetime.utcnow() - timedelta(hours=3))

    job = runner.claim(db_session, runner.KIND_DRY_RUN)

    assert job.state == runner.JOB_RUNNING
    row = db_session.get(JiraMigrationReport, report_id)
    assert row.status == store.STATUS_FAILED
    assert row.error == runner.RUN_INTERRUPTED


# --- Пробный прогон ------------------------------------------------------------

async def test_dry_run_job_saves_report(db_session):
    seed_world(db_session)
    job = runner.claim(db_session, runner.KIND_DRY_RUN)

    await runner.run_dry_run(job, session_factory=_session(db_session), jira_factory=lambda db: dc_world())

    assert (job.state, job.error) == ("done", None)
    assert job.counters["worklogs_read"] == 5
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_DONE
    assert store.report_data(row)["offset_hours"] == 3
    assert store.report_maps(row)["issues"]["OS-91030"] == "258783"


async def test_dry_run_job_records_probe_failure(db_session):
    seed_world(db_session)
    job = runner.claim(db_session, runner.KIND_DRY_RUN)

    await runner.run_dry_run(
        job, session_factory=_session(db_session),
        jira_factory=lambda db: dc_world(fail={"get_projects"}),
    )

    assert job.state == "error" and "Список проектов" in job.error
    row = store.latest_report(db_session)
    assert row.status == store.STATUS_FAILED
    assert any(p["code"] == "projects" and not p["ok"] for p in store.report_data(row)["probe"])


async def test_dry_run_job_without_credentials(db_session):
    def no_credentials(db):
        raise JiraClientError("Missing Jira credentials")

    job = runner.claim(db_session, runner.KIND_DRY_RUN)
    await runner.run_dry_run(job, session_factory=_session(db_session), jira_factory=no_credentials)

    assert job.state == "error"
    assert job.error.startswith("Новая Jira недоступна")
    assert "credentials" not in job.error
    assert store.latest_report(db_session).status == store.STATUS_FAILED


async def test_dry_run_job_unexpected_error_is_generic(db_session, monkeypatch):
    """Поломка в коде: отчёт неудачный, текст — общий, без подробностей исключения."""
    seed_world(db_session)

    async def broken(*args, **kwargs):
        raise KeyError("secret internals")

    monkeypatch.setattr(runner, "build_report", broken)
    job = runner.claim(db_session, runner.KIND_DRY_RUN)

    await runner.run_dry_run(job, session_factory=_session(db_session), jira_factory=lambda db: dc_world())

    assert (job.state, job.error) == ("error", runner.DRY_RUN_FAILED)
    row = store.latest_report(db_session)
    assert (row.status, row.error) == (store.STATUS_FAILED, runner.DRY_RUN_FAILED)


async def test_dry_run_job_fails_without_session(db_session):
    job = runner.claim(db_session, runner.KIND_DRY_RUN)

    await runner.run_dry_run(job, session_factory=_broken_session, jira_factory=lambda db: dc_world())

    assert (job.state, job.error) == ("error", runner.DRY_RUN_FAILED)


# --- Применение ----------------------------------------------------------------

async def test_apply_job_commits_and_starts_full_sync(db_session, monkeypatch):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    full_sync = AsyncMock(return_value="run-1")
    monkeypatch.setattr(runner, "run_full_sync", full_sync)
    job = runner.claim(db_session, runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert (job.state, job.kind) == ("done", runner.KIND_APPLY)
    assert job.counters["issues_deleted"] == 2
    assert get_migration_state(db_session) == STATE_DONE
    full_sync.assert_awaited_once()
    assert full_sync.await_args.args[2] == date(2026, 9, 9)


async def test_apply_job_refused_keeps_database(db_session, monkeypatch):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=30))
    full_sync = AsyncMock()
    monkeypatch.setattr(runner, "run_full_sync", full_sync)
    job = runner.claim(db_session, runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert job.state == "error" and "старше суток" in job.error
    assert get_migration_state(db_session) == STATE_PENDING
    full_sync.assert_not_awaited()


async def test_apply_job_unexpected_error_is_generic(db_session, monkeypatch):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    full_sync = AsyncMock()
    monkeypatch.setattr(runner, "run_full_sync", full_sync)

    def broken(*args, **kwargs):
        raise KeyError("secret internals")

    monkeypatch.setattr(runner, "apply_migration", broken)
    job = runner.claim(db_session, runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert (job.state, job.error) == ("error", runner.APPLY_FAILED)
    assert get_migration_state(db_session) == STATE_PENDING
    full_sync.assert_not_awaited()


async def test_apply_job_done_even_if_full_sync_fails_to_start(db_session, monkeypatch):
    """База уже перепривязана: сбой запуска синхронизации не делает применение ошибкой."""
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    monkeypatch.setattr(runner, "run_full_sync", AsyncMock(side_effect=RuntimeError("boom")))
    job = runner.claim(db_session, runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert (job.state, job.error) == ("done", None)
    assert get_migration_state(db_session) == STATE_DONE
    sync_job = runner.current_job()
    assert (sync_job.kind, sync_job.state, sync_job.error) == (
        runner.KIND_FULL_SYNC, "error", runner.FULL_SYNC_FAILED,
    )


async def test_apply_hands_slot_over_to_full_sync(db_session, monkeypatch):
    """Пока идёт синхронизация после применения, слот занят: второй запуск — отказ."""
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    run_id = SyncRunRepository(db_session).create(mode="full", trigger="manual").id
    seen: dict = {}

    async def full_sync(*args, **kwargs):
        current = runner.current_job()
        seen["during"] = (current.kind, current.state)
        with pytest.raises(RuntimeError):
            runner.claim(db_session, runner.KIND_FULL_SYNC)
        SyncRunRepository(db_session).finalize(run_id, status="ok", stages=[])
        return run_id

    monkeypatch.setattr(runner, "run_full_sync", full_sync)
    job = runner.claim(db_session, runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_session(db_session),
        jira_factory=lambda db: FakeJira(),
    )

    assert seen["during"] == (runner.KIND_FULL_SYNC, runner.JOB_RUNNING)
    assert (job.kind, job.state) == (runner.KIND_APPLY, runner.JOB_DONE)
    after = runner.current_job()
    assert (after.kind, after.state, after.error) == (runner.KIND_FULL_SYNC, runner.JOB_DONE, None)


async def test_apply_job_fails_without_session(db_session):
    job = runner.claim(db_session, runner.KIND_APPLY)

    await runner.run_apply(
        job, backup_confirmed=True, session_factory=_broken_session, jira_factory=lambda db: FakeJira(),
    )

    assert (job.state, job.error) == ("error", runner.APPLY_FAILED)


# --- Полная синхронизация после применения -------------------------------------

async def test_full_sync_reloads_worklogs_from_earliest_date(db_session, monkeypatch):
    report_id = _done_with_report(db_session)
    captured: dict = {}

    async def fake_run(self, *, mode, trigger, team=None, run_id=None):
        captured["stages"] = self.stages
        captured["mode"] = mode
        return {"status": "ok", "stages": []}

    monkeypatch.setattr(PipelineOrchestrator, "run", fake_run)

    run_id = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    stage = next(s for s in captured["stages"] if isinstance(s, WorklogsFullStage))
    assert stage.since == date(2020, 2, 26)
    assert captured["mode"] == "full"
    run = db_session.get(SyncRun, run_id)
    assert (run.status, run.mode, run.trigger) == ("ok", "full", "manual")
    assert db_session.get(JiraMigrationReport, report_id).sync_run_id == run_id
    assert SyncLock(db_session).current_run_id() is None


async def test_full_sync_skipped_while_other_sync_runs(db_session):
    report_id = _done_with_report(db_session)
    SyncLock(db_session).acquire("other-run")

    result = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    assert result is None
    assert db_session.get(JiraMigrationReport, report_id).sync_run_id is None


async def test_full_sync_keeps_lock_fresh_between_stages(db_session, monkeypatch):
    """Перед каждой стадией блокировка продлевается: долгая стадия не делает её «зависшей»."""
    report_id = _done_with_report(db_session)
    seen: dict = {}

    async def slow():
        SyncLock(db_session)._set_started_at(datetime.utcnow() - timedelta(minutes=90))

    async def next_stage():
        seen["stale"] = SyncLock(db_session).is_stale()

    monkeypatch.setattr(
        runner, "build_pipeline",
        lambda **kwargs: [_Step("slow", slow), _Step("next", next_stage)],
    )

    run_id = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    assert seen["stale"] is False
    assert db_session.get(SyncRun, run_id).status == "ok"


async def test_full_sync_keeps_lock_fresh_inside_long_stage(db_session, monkeypatch):
    """Внутри стадии блокировку продлевает опрос синка между страницами Jira."""
    report_id = _done_with_report(db_session)
    monkeypatch.setattr(runner, "LOCK_HEARTBEAT_EVERY", timedelta(0))
    seen: dict = {}

    def pipeline(**kwargs):
        sync = kwargs["services"]["sync"]

        async def long_stage():
            SyncLock(db_session)._set_started_at(datetime.utcnow() - timedelta(minutes=90))
            await sync._check_cancelled()
            seen["stale"] = SyncLock(db_session).is_stale()

        return [_Step("worklogs", long_stage)]

    monkeypatch.setattr(runner, "build_pipeline", pipeline)

    await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    assert seen["stale"] is False


async def test_full_sync_failure_is_recorded_and_lock_released(db_session, monkeypatch):
    report_id = _done_with_report(db_session)

    def no_credentials(db):
        raise JiraClientError("Missing Jira credentials")

    run_id = await runner.run_full_sync(db_session, report_id, date(2020, 2, 26), jira_factory=no_credentials)

    run = db_session.get(SyncRun, run_id)
    assert (run.status, run.error_text) == ("failed", runner.FULL_SYNC_ERROR)
    assert SyncLock(db_session).current_run_id() is None


async def test_full_sync_stage_error_stored_as_generic_text(db_session, monkeypatch):
    """Текст исключения стадии — в журнал сервера; в истории и на странице — общий текст по-русски."""
    report_id = _done_with_report(db_session)

    async def broken():
        raise KeyError("secret internals")

    monkeypatch.setattr(runner, "build_pipeline", lambda **kwargs: [_Step("worklogs", broken)])

    run_id = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    run = db_session.get(SyncRun, run_id)
    assert (run.status, run.error_text) == ("failed", runner.FULL_SYNC_ERROR)


def test_run_error_text_keeps_known_messages():
    assert runner.run_error_text(None) is None
    assert runner.run_error_text(runner.LOCK_LOST) == runner.LOCK_LOST
    assert runner.run_error_text(runner.SYNC_INTERRUPTED) == runner.SYNC_INTERRUPTED
    assert runner.run_error_text("'NoneType' object has no attribute 'id'") == runner.FULL_SYNC_ERROR


async def test_full_sync_stops_when_lock_taken_by_other_run(db_session, monkeypatch):
    """Блокировку забрал другой запуск — синхронизация останавливается, чужую блокировку не снимает."""
    report_id = _done_with_report(db_session, applied=True)
    seen: dict = {}

    async def steal():
        _steal_lock(db_session)

    async def after():
        seen["ran"] = True

    monkeypatch.setattr(
        runner, "build_pipeline", lambda **kwargs: [_Step("first", steal), _Step("second", after)],
    )
    job = runner.claim(db_session, runner.KIND_FULL_SYNC)

    await runner.restart_full_sync(job, session_factory=_session(db_session), jira_factory=lambda db: FakeJira())

    assert "ran" not in seen
    run = db_session.get(SyncRun, db_session.get(JiraMigrationReport, report_id).sync_run_id)
    assert (run.status, run.error_text) == ("failed", runner.LOCK_LOST)
    assert (job.state, job.error) == ("error", runner.LOCK_LOST)
    assert SyncLock(db_session).current_run_id() == "other-run"


async def test_full_sync_stops_inside_stage_when_lock_lost(db_session, monkeypatch):
    report_id = _done_with_report(db_session)
    monkeypatch.setattr(runner, "LOCK_HEARTBEAT_EVERY", timedelta(0))

    def pipeline(**kwargs):
        sync = kwargs["services"]["sync"]

        async def long_stage():
            _steal_lock(db_session)
            await sync._check_cancelled()

        return [_Step("worklogs", long_stage)]

    monkeypatch.setattr(runner, "build_pipeline", pipeline)

    run_id = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    run = db_session.get(SyncRun, run_id)
    assert (run.status, run.error_text) == ("failed", runner.LOCK_LOST)
    assert SyncLock(db_session).current_run_id() == "other-run"


async def test_full_sync_releases_lock_when_report_link_fails(db_session, monkeypatch):
    report_id = _done_with_report(db_session)

    def broken(*args, **kwargs):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(store, "set_sync_run", broken)

    run_id = await runner.run_full_sync(
        db_session, report_id, date(2020, 2, 26), jira_factory=lambda db: FakeJira(),
    )

    assert db_session.get(SyncRun, run_id).status == "failed"
    assert SyncLock(db_session).current_run_id() is None


def _interrupted_run(db, report_id):
    """Запуск полной синхронизации, оборванный перезапуском сервиса: «идёт» и держит свежую блокировку."""
    run_id = SyncRunRepository(db).create(mode="full", trigger="manual").id
    store.set_sync_run(db, report_id, run_id)
    assert SyncLock(db).acquire(run_id)
    return run_id


async def _pipeline_ok(self, *, mode, trigger, team=None, run_id=None):
    return {"status": "ok", "stages": []}


async def test_restart_takes_over_lock_of_interrupted_run(db_session, monkeypatch):
    """Блокировку держит прерванный запуск этого же переезда — повтор не ждёт её зависания."""
    report_id = _done_with_report(db_session, applied=True)
    dead = _interrupted_run(db_session, report_id)
    monkeypatch.setattr(PipelineOrchestrator, "run", _pipeline_ok)
    job = runner.claim(db_session, runner.KIND_FULL_SYNC)

    await runner.restart_full_sync(job, session_factory=_session(db_session), jira_factory=lambda db: FakeJira())

    assert (job.state, job.error) == (runner.JOB_DONE, None)
    new_id = db_session.get(JiraMigrationReport, report_id).sync_run_id
    assert new_id != dead
    assert db_session.get(SyncRun, new_id).status == "ok"
    old = db_session.get(SyncRun, dead)
    assert (old.status, old.error_text) == ("failed", runner.SYNC_INTERRUPTED)
    assert SyncLock(db_session).current_run_id() is None


async def test_restart_leaves_lock_of_other_sync_alone(db_session, monkeypatch):
    """Блокировку держит чужой запуск (например, по расписанию) — повтор не стартует и её не трогает."""
    report_id = _done_with_report(db_session, applied=True)
    dead = _interrupted_run(db_session, report_id)
    _steal_lock(db_session)
    monkeypatch.setattr(PipelineOrchestrator, "run", _pipeline_ok)
    job = runner.claim(db_session, runner.KIND_FULL_SYNC)

    await runner.restart_full_sync(job, session_factory=_session(db_session), jira_factory=lambda db: FakeJira())

    assert (job.state, job.error) == (runner.JOB_ERROR, runner.SYNC_BUSY)
    assert SyncLock(db_session).current_run_id() == "other-run"
    assert db_session.get(JiraMigrationReport, report_id).sync_run_id == dead


async def test_restart_full_sync_holds_slot_and_reports_busy(db_session, monkeypatch):
    _done_with_report(db_session, applied=True)
    monkeypatch.setattr(runner, "run_full_sync", AsyncMock(return_value=None))
    job = runner.claim(db_session, runner.KIND_FULL_SYNC)
    with pytest.raises(RuntimeError):
        runner.claim(db_session, runner.KIND_FULL_SYNC)

    await runner.restart_full_sync(job, session_factory=_session(db_session), jira_factory=lambda db: FakeJira())

    assert (job.state, job.error) == ("error", runner.SYNC_BUSY)


async def test_restart_full_sync_requires_applied_migration(db_session, monkeypatch):
    _done_with_report(db_session)
    full_sync = AsyncMock()
    monkeypatch.setattr(runner, "run_full_sync", full_sync)
    job = runner.claim(db_session, runner.KIND_FULL_SYNC)

    await runner.restart_full_sync(job, session_factory=_session(db_session), jira_factory=lambda db: FakeJira())

    assert (job.state, job.error) == ("error", runner.FULL_SYNC_NOT_APPLIED)
    full_sync.assert_not_awaited()


def test_worklogs_since_is_day_before_earliest():
    assert runner.worklogs_since({"db_worklogs_min_date": "2020-02-27"}) == date(2020, 2, 26)
    assert runner.worklogs_since({}) == date.today() - timedelta(days=runner.DEFAULT_WORKLOG_DAYS + 1)


# --- Отдельный поток -----------------------------------------------------------

def test_start_runs_operation_in_own_thread_and_loop(monkeypatch):
    seen: dict = {}

    async def fake_dry_run(job):
        seen["thread"] = threading.current_thread()
        seen["loop"] = asyncio.get_running_loop()

    monkeypatch.setattr(runner, "run_dry_run", fake_dry_run)
    job = runner.MigrationJob(kind=runner.KIND_DRY_RUN, state=runner.JOB_RUNNING)

    runner.start_dry_run(job).join(timeout=10)

    assert seen["thread"] is not threading.current_thread()
    assert seen["loop"] is not None


async def test_service_loop_bus_forwards_events_to_service_loop(monkeypatch):
    """События синка из потока операции попадают подписчикам в цикле сервиса."""
    from app.services import event_bus

    bus = event_bus.EventBroadcaster()
    monkeypatch.setattr(event_bus, "_instance", bus)
    queue = bus.subscribe()
    forwarding = runner._ServiceLoopBus(asyncio.get_running_loop())

    thread = threading.Thread(target=lambda: asyncio.run(forwarding.publish({"type": "stage_start"})))
    thread.start()
    thread.join(timeout=10)

    assert await asyncio.wait_for(queue.get(), timeout=5) == {"type": "stage_start"}


# --- Сверка после ----------------------------------------------------------------

def test_post_check_latest(db_session):
    seed_ready(db_session, datetime.utcnow() - timedelta(hours=1))
    with pytest.raises(ValueError):
        runner.post_check_latest(db_session, now=datetime(2026, 10, 15, 9, 0))
    row = store.latest_report(db_session)
    row.applied_at = datetime(2026, 10, 14, 13, 0)
    db_session.commit()

    result = runner.post_check_latest(db_session, now=datetime(2026, 10, 15, 9, 0))

    assert result["rows"][0]["db_hours"] == 1.0
    assert store.post_check_data(store.latest_report(db_session)) == result
