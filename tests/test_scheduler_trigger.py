"""Tests for scheduled_pipeline_runner (T20)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.scheduler import scheduled_pipeline_runner


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _make_db(session):
    """Return a callable that yields the given db_session (replaces _get_db_session)."""
    return lambda: session


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
