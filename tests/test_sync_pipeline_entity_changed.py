"""PipelineOrchestrator публикует entity_changed после pipeline_done."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sync_pipeline import PipelineOrchestrator, Stage


class _DummyStage(Stage):
    name = "test"
    critical = True

    def __init__(self, inv):
        self._inv = inv

    async def run(self, ctx):
        return {"count": 1}

    def invalidates(self):
        return self._inv


@pytest.mark.asyncio
async def test_pipeline_publishes_entity_changed_on_success():
    bus = AsyncMock()
    db = MagicMock()
    stages = [
        _DummyStage(["issues", "tree", "backlog"]),
        _DummyStage(["worklogs", "capacity"]),
    ]
    orch = PipelineOrchestrator(stages=stages, db=db, bus=bus)
    result = await orch.run(mode="full", trigger="manual", run_id="r1")

    assert result["status"] == "ok"

    entity_changed_calls = [
        call for call in bus.publish.call_args_list
        if call.args[0].get("type") == "entity_changed"
    ]
    assert len(entity_changed_calls) == 1

    published_entities = set(entity_changed_calls[0].args[0]["entities"])
    assert "issues" in published_entities
    assert "backlog" in published_entities
    assert "worklogs" in published_entities
    assert "capacity" in published_entities


@pytest.mark.asyncio
async def test_pipeline_publishes_entity_changed_on_partial():
    bus = AsyncMock()
    db = MagicMock()

    class _FailStage(Stage):
        name = "fail"
        critical = False

        async def run(self, ctx):
            raise RuntimeError("oops")

        def invalidates(self):
            return []

    stages = [_DummyStage(["issues"]), _FailStage()]
    orch = PipelineOrchestrator(stages=stages, db=db, bus=bus)
    result = await orch.run(mode="full", trigger="manual", run_id="r2")

    assert result["status"] == "partial"
    entity_changed_calls = [
        call for call in bus.publish.call_args_list
        if call.args[0].get("type") == "entity_changed"
    ]
    assert len(entity_changed_calls) == 1
    assert "issues" in entity_changed_calls[0].args[0]["entities"]
