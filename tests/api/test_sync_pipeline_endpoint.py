"""Tests for POST /sync/pipeline endpoint."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


def _make_fake_jira_cm():
    """Return a context-manager mock that yields a fake JiraClient."""
    fake_jira = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_jira)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_pipeline_endpoint_streams_sse_events():
    """POST /sync/pipeline normal-mode: streams pipeline_done SSE event."""
    fake_orch_run = AsyncMock(return_value={"status": "ok", "stages": []})

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch, \
         patch("app.api.endpoints.sync.JiraClient.from_db", return_value=_make_fake_jira_cm()):
        build_orch.return_value.run = fake_orch_run

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/v1/sync/pipeline",
                json={"mode": "normal"},
                timeout=5.0,
            ) as resp:
                assert resp.status_code == 200
                body = ""
                async for chunk in resp.aiter_text():
                    body += chunk
                    if "pipeline_done" in body:
                        break
                assert "pipeline_done" in body or "run_id" in body


@pytest.mark.asyncio
async def test_pipeline_returns_409_when_lock_held(db_session):
    """If lock is held by another run, returns 409 with running_run_id."""
    from app.database import get_db
    from app.services.sync_lock import SyncLock

    SyncLock(db_session).acquire("other-run")

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v1/sync/pipeline", json={"mode": "quick"})
        assert resp.status_code == 409
        body = resp.json()
        # FastAPI wraps HTTPException detail in {"detail": ...}
        detail = body.get("detail", body)
        assert "running_run_id" in detail
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jira_client_stays_alive_during_pipeline():
    """JiraClient context manager is entered inside the SSE stream, not before it."""
    fake_orch_run = AsyncMock(return_value={"status": "ok", "stages": []})
    fake_cm = _make_fake_jira_cm()

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch, \
         patch("app.api.endpoints.sync.JiraClient.from_db", return_value=fake_cm) as from_db_mock:
        build_orch.return_value.run = fake_orch_run

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            async with client.stream(
                "POST",
                "/api/v1/sync/pipeline",
                json={"mode": "quick"},
                timeout=5.0,
            ) as resp:
                body = ""
                async for chunk in resp.aiter_text():
                    body += chunk
                    if "pipeline_done" in body:
                        break

        # JiraClient was opened (entered) exactly once
        fake_cm.__aenter__.assert_awaited_once()
        # JiraClient was closed (exited) after the stream completed
        fake_cm.__aexit__.assert_awaited_once()
        # _build_orchestrator was called with the jira instance
        build_orch.assert_called_once()
