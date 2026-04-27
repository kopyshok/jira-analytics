"""SSE endpoint for global event stream."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()

PING_INTERVAL_SEC = 30


@router.get("/stream")
async def event_stream(request: Request) -> StreamingResponse:
    """Глобальный SSE-канал: stage_done, entity_changed, sync_started, sync_finished."""
    bus = get_event_bus()
    queue = bus.subscribe()

    async def event_generator():
        try:
            yield ":connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_INTERVAL_SEC)
                    payload = json.dumps(event)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ":ping\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
