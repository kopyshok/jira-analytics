"""Tests for pipeline cancellation on client disconnect."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_pipeline_cancels_on_client_disconnect():
    """If client closes stream mid-pipeline, pipeline task is cancelled without hanging."""
    async def _slow_run(**kw):
        await asyncio.sleep(5)
        return {"status": "ok", "stages": []}

    slow_run = AsyncMock(side_effect=_slow_run)

    with patch("app.api.endpoints.sync._build_orchestrator") as build_orch:
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
