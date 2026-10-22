"""Tests for scheduled_pipeline_runner (T20)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import SyncSchedule
from app.services import sync_lock
from app.services.scheduler import scheduled_pipeline_runner
from app.services.sync_lock import SyncLock
from app.services.sync_pipeline import Stage


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_db(session):
    """Return a callable that yields the given db_session (replaces _get_db_session)."""
    return lambda: session


def _seed_schedule(db, schedule_id: str):
    """Реальное расписание: запуск ссылается на него, Postgres проверяет ссылку."""
    db.add(SyncSchedule(
        id=schedule_id,
        name=f"Расписание {schedule_id}",
        cron_expr="0 3 * * *",
        mode="quick",
        enabled=True,
    ))
    db.flush()


def _make_jira_ctx():
    """Fake async context manager for JiraClient.from_db."""
    jira = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=jira)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, jira


# ------------------------------------------------------------------
# T20-a: skip when lock held
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_runner_skips_when_lock_held(db_session):
    from app.services.sync_lock import SyncLock

    _seed_schedule(db_session, "sched-1")

    # Установить lock вручную
    lock = SyncLock(db_session)
    lock.acquire("fake-running-id")

    with patch(
        "app.services.scheduler._get_db_session",
        return_value=db_session,
    ):
        # JiraClient.from_db не должен вызываться при skip
        with patch("app.services.scheduler.JiraClient") as mock_jira_cls:
            await scheduled_pipeline_runner(
                schedule_id="sched-1",
                mode="quick",
                team=None,
            )
            mock_jira_cls.from_db.assert_not_called()

    from app.repositories.sync_run import SyncRunRepository
    repo = SyncRunRepository(db_session)
    runs = repo.list_latest(limit=10)
    assert len(runs) >= 1
    skipped = [r for r in runs if r.status == "skipped"]
    assert len(skipped) == 1
    assert skipped[0].error_text == "previous_running"
    assert skipped[0].trigger == "scheduled"


# ------------------------------------------------------------------
# T20-b: normal run — calls orchestrator
# ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_trigger_runner_creates_run_and_calls_orchestrator(db_session):
    _seed_schedule(db_session, "sched-2")
    jira_ctx, jira_mock = _make_jira_ctx()

    mock_orch = MagicMock()
    mock_orch.run = AsyncMock(return_value={"status": "ok", "stages": []})

    with patch("app.services.scheduler._get_db_session", return_value=db_session):
        with patch("app.services.scheduler.JiraClient") as mock_jira_cls:
            mock_jira_cls.from_db.return_value = jira_ctx
            with patch(
                "app.services.scheduler._build_orchestrator_local",
                return_value=mock_orch,
            ):
                await scheduled_pipeline_runner(
                    schedule_id="sched-2",
                    mode="normal",
                    team=None,
                )

    from app.repositories.sync_run import SyncRunRepository
    repo = SyncRunRepository(db_session)
    runs = repo.list_latest(limit=10)
    assert len(runs) == 1
    run = runs[0]
    assert run.status == "ok"
    assert run.trigger == "scheduled"
    assert run.mode == "normal"
    assert run.schedule_id == "sched-2"

    mock_orch.run.assert_awaited_once()
    call_kwargs = mock_orch.run.call_args.kwargs
    assert call_kwargs["mode"] == "normal"
    assert call_kwargs["trigger"] == "scheduled"


# ------------------------------------------------------------------
# Долгий запуск: блокировка продлевается, чужая не снимается
# ------------------------------------------------------------------

class _Step(Stage):
    """Стадия-подмена: выполняет переданное действие."""

    critical = True

    def __init__(self, name, action):
        self.name = name
        self.action = action

    async def run(self, ctx):
        await self.action()
        return {}


async def _run_scheduled(db_session, schedule_id, pipeline):
    jira_ctx, _ = _make_jira_ctx()
    with patch("app.services.scheduler._get_db_session", return_value=db_session), \
         patch("app.services.scheduler.JiraClient") as mock_jira_cls, \
         patch("app.services.sync_pipeline.build_pipeline", side_effect=pipeline):
        mock_jira_cls.from_db.return_value = jira_ctx
        await scheduled_pipeline_runner(schedule_id=schedule_id, mode="normal", team=None)


@pytest.mark.asyncio
async def test_scheduled_run_keeps_lock_fresh_inside_long_stage(db_session, monkeypatch):
    """Синк дольше часа не выглядит брошенным: объединение двойников и
    следующий запуск ждут его окончания, а не вклиниваются посреди."""
    _seed_schedule(db_session, "sched-long")
    monkeypatch.setattr(sync_lock, "HEARTBEAT_EVERY", timedelta(0))
    seen: dict = {}

    def pipeline(**kwargs):
        sync = kwargs["services"]["sync"]

        async def long_stage():
            SyncLock(db_session)._set_started_at(datetime.utcnow() - timedelta(minutes=90))
            await sync._check_cancelled()
            seen["stale"] = SyncLock(db_session).is_stale()

        return [_Step("issues", long_stage)]

    await _run_scheduled(db_session, "sched-long", pipeline)

    assert seen["stale"] is False


@pytest.mark.asyncio
async def test_scheduled_run_stops_and_keeps_lock_taken_by_other_run(db_session):
    _seed_schedule(db_session, "sched-steal")
    seen: dict = {}

    async def steal():
        SyncLock(db_session)._write({"run_id": "other-run", "started_at": datetime.utcnow().isoformat()})

    async def after():
        seen["ran"] = True

    await _run_scheduled(
        db_session, "sched-steal", lambda **kw: [_Step("issues", steal), _Step("worklogs", after)],
    )

    assert "ran" not in seen
    assert SyncLock(db_session).current_run_id() == "other-run"
    from app.repositories.sync_run import SyncRunRepository
    [run] = [r for r in SyncRunRepository(db_session).list_latest(limit=10) if r.schedule_id == "sched-steal"]
    assert run.status == "failed"


def test_close_interrupted_runs_after_restart(db_session):
    """После перезапуска сервиса ни один запуск не идёт: «Выполняется» закрываются
    как прерванные, блокировка снимается — следующий синк не ждёт час."""
    from app.repositories.sync_run import SyncRunRepository
    from app.services.scheduler import RUN_INTERRUPTED, close_interrupted_runs

    repo = SyncRunRepository(db_session)
    hung = repo.create(mode="normal", trigger="manual")
    done = repo.create(mode="normal", trigger="scheduled")
    repo.finalize(done.id, status="ok", stages=[])
    SyncLock(db_session).acquire(hung.id)

    assert close_interrupted_runs(db_session) == 1

    assert (repo.get(hung.id).status, repo.get(hung.id).error_text) == ("failed", RUN_INTERRUPTED)
    assert repo.get(done.id).status == "ok"
    assert SyncLock(db_session).current_run_id() is None
