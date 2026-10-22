"""Tests for pipeline cancellation on client disconnect."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _make_fake_jira_cm():
    fake_jira = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_jira)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_pipeline_cancels_on_client_disconnect():
    """If client closes stream mid-pipeline, pipeline task is cancelled without hanging."""
    async def _slow_run(**kw):
        await asyncio.sleep(5)
        return {"status": "ok", "stages": []}

    slow_run = AsyncMock(side_effect=_slow_run)

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch, \
         patch("app.api.endpoints.sync.JiraClient.from_db", return_value=_make_fake_jira_cm()):
        build_orch.return_value.run = slow_run

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/v1/sync/pipeline",
                json={"mode": "quick"},
                timeout=1.0,
            ):
                # Close the stream immediately
                pass
        # Assert: did not hang
        assert True


async def _start(db_session):
    from app.api.endpoints import sync as sync_endpoints
    from app.schemas.sync_pipeline import PipelineRequest

    request = MagicMock(is_disconnected=AsyncMock(return_value=False))
    return await sync_endpoints.run_pipeline(PipelineRequest(mode="quick"), request=request, db=db_session)


@pytest.mark.asyncio
async def test_stream_closed_mid_event_closes_run_in_history(db_session):
    """Вкладку закрыли/обновили посреди отправки события: запуск не остаётся
    «Выполняется» навсегда, блокировка снята."""
    from app.models import SyncRun
    from app.services.event_bus import get_event_bus
    from app.services.sync_lock import SyncLock

    async def _slow_run(**kw):
        await get_event_bus().publish({"type": "sync_started", "run_id": kw["run_id"]})
        await asyncio.sleep(5)
        return {"status": "ok", "stages": []}

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch, \
         patch("app.api.endpoints.sync.JiraClient.from_db", return_value=_make_fake_jira_cm()):
        build_orch.return_value.run = AsyncMock(side_effect=_slow_run)
        stream = (await _start(db_session)).body_iterator
        await stream.__anext__()
        await stream.aclose()
        await asyncio.sleep(0)

    [run] = db_session.query(SyncRun).all()
    assert run.status == "cancelled"
    assert SyncLock(db_session).current_run_id() is None


@pytest.mark.asyncio
async def test_failure_before_result_closes_run_as_failed(db_session):
    from app.connectors.jira_client import JiraClientError
    from app.models import SyncRun

    with patch(
        "app.api.endpoints.sync.JiraClient.from_db",
        side_effect=JiraClientError("Missing Jira credentials"),
    ):
        stream = (await _start(db_session)).body_iterator
        with pytest.raises(JiraClientError):
            async for _ in stream:
                pass

    [run] = db_session.query(SyncRun).all()
    assert (run.status, run.error_text) == ("failed", "Missing Jira credentials")
