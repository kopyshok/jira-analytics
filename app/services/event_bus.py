"""EventBroadcaster — in-memory pub/sub для SSE-канала.

Один процесс, single-user MVP. Каждый подписчик — свой asyncio.Queue.
При переполнении очереди дропаем старые события (subscriber слишком медленный).
"""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBroadcaster:
    def __init__(self, queue_size: int = 100) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._queue_size = queue_size
        self._lock = asyncio.Lock()

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        try:
            self._subscribers.remove(queue)
        except ValueError:
            pass

    async def publish(self, event: dict[str, Any]) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest, push newest
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    logger.warning("event_bus: subscriber queue still full, dropping event")


# Singleton — единственный процесс, один EventBroadcaster
_instance: EventBroadcaster | None = None


def get_event_bus() -> EventBroadcaster:
    global _instance
    if _instance is None:
        _instance = EventBroadcaster()
    return _instance
