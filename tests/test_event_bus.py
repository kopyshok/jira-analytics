"""Tests for EventBroadcaster pub/sub."""

import asyncio

import pytest

from app.services.event_bus import EventBroadcaster


@pytest.mark.asyncio
async def test_subscribe_and_receive_published_event():
    bus = EventBroadcaster()
    queue = bus.subscribe()
    await bus.publish({"type": "stage_done", "stage": "projects"})
    event = await asyncio.wait_for(queue.get(), timeout=1.0)
    assert event["stage"] == "projects"


@pytest.mark.asyncio
async def test_multiple_subscribers_each_get_event():
    bus = EventBroadcaster()
    q1 = bus.subscribe()
    q2 = bus.subscribe()
    await bus.publish({"type": "ping"})
    e1 = await asyncio.wait_for(q1.get(), timeout=1.0)
    e2 = await asyncio.wait_for(q2.get(), timeout=1.0)
    assert e1["type"] == "ping"
    assert e2["type"] == "ping"


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    bus = EventBroadcaster()
    queue = bus.subscribe()
    bus.unsubscribe(queue)
    await bus.publish({"type": "x"})
    assert queue.empty()


@pytest.mark.asyncio
async def test_slow_consumer_drops_oldest_when_full(caplog):
    bus = EventBroadcaster(queue_size=2)
    queue = bus.subscribe()
    for i in range(5):
        await bus.publish({"type": "e", "i": i})
    # Очередь не должна заблокировать публикацию
    assert queue.qsize() <= 2
