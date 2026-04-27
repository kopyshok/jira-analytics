"""Tests for POST /sync/pipeline endpoint."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_pipeline_endpoint_streams_sse_events():
    """POST /sync/pipeline normal-mode: streams pipeline_done SSE event."""
    fake_orch_run = AsyncMock(return_value={"status": "ok", "stages": []})

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch:
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
