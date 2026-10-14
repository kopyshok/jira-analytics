"""Tests for PipelineOrchestrator skeleton."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sync_pipeline import PipelineOrchestrator, Stage


class FakeStage(Stage):
    name = "fake"
    critical = True

    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.calls = 0

    async def run(self, ctx):
        self.calls += 1
        if self.should_fail:
            raise RuntimeError("boom")
        return {"items": 1}

    def invalidates(self):
        return ["fake_key"]


@pytest.mark.asyncio
async def test_orchestrator_runs_stages_in_order():
    s1 = FakeStage()
    s2 = FakeStage()
    orch = PipelineOrchestrator(stages=[s1, s2], db=MagicMock(), bus=MagicMock(publish=AsyncMock()))
    result = await orch.run(mode="normal", trigger="manual")
    assert s1.calls == 1
    assert s2.calls == 1
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_orchestrator_stops_on_critical_failure():
    s_ok = FakeStage()
    s_fail = FakeStage(should_fail=True)
    s_after = FakeStage()
    orch = PipelineOrchestrator(stages=[s_ok, s_fail, s_after], db=MagicMock(), bus=MagicMock(publish=AsyncMock()))
    result = await orch.run(mode="normal", trigger="manual")
    assert s_ok.calls == 1
    assert s_fail.calls == 1
    assert s_after.calls == 0
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_non_critical_failure_continues_with_partial():
    s_ok = FakeStage()
    s_fail = FakeStage(should_fail=True)
    s_fail.critical = False
    s_after = FakeStage()
    orch = PipelineOrchestrator(stages=[s_ok, s_fail, s_after], db=MagicMock(), bus=MagicMock(publish=AsyncMock()))
    result = await orch.run(mode="normal", trigger="manual")
    assert s_ok.calls == 1
    assert s_fail.calls == 1
    assert s_after.calls == 1
    assert result["status"] == "partial"


@pytest.mark.asyncio
async def test_publishes_stage_done_with_invalidates():
    s = FakeStage()
    bus = MagicMock(publish=AsyncMock())
    orch = PipelineOrchestrator(stages=[s], db=MagicMock(), bus=bus)
    await orch.run(mode="normal", trigger="manual")
    published = [c.args[0] for c in bus.publish.call_args_list]
    stage_done = [e for e in published if e.get("type") == "stage_done"]
    assert any(e["invalidates"] == ["fake_key"] for e in stage_done)


@pytest.mark.asyncio
async def test_before_stage_called_before_each_stage():
    order: list[str] = []
    s1 = FakeStage()
    s2 = FakeStage()
    s1.run = AsyncMock(side_effect=lambda ctx: order.append("s1"))
    s2.run = AsyncMock(side_effect=lambda ctx: order.append("s2"))
    orch = PipelineOrchestrator(
        stages=[s1, s2], db=MagicMock(), bus=MagicMock(publish=AsyncMock()),
        before_stage=lambda: order.append("before"),
    )
    await orch.run(mode="full", trigger="manual")
    assert order == ["before", "s1", "before", "s2"]


@pytest.mark.asyncio
async def test_before_stage_failure_does_not_stop_pipeline():
    """Сбой подготовки к стадии — в журнал, сессия откатывается, стадии идут дальше."""
    s1 = FakeStage()
    s2 = FakeStage()
    db = MagicMock()
    bus = MagicMock(publish=AsyncMock())

    def broken():
        raise RuntimeError("db down")

    orch = PipelineOrchestrator(stages=[s1, s2], db=db, bus=bus, before_stage=broken)
    result = await orch.run(mode="full", trigger="manual")

    assert (s1.calls, s2.calls) == (1, 1)
    assert result["status"] == "ok"
    db.rollback.assert_called()
    published = [c.args[0] for c in bus.publish.call_args_list]
    assert published[-1] == {"type": "pipeline_done", "run_id": None, "status": "ok"}


@pytest.mark.asyncio
async def test_before_stage_abort_stops_pipeline_with_message():
    from app.services.sync_pipeline import PipelineAborted

    s1 = FakeStage()
    bus = MagicMock(publish=AsyncMock())

    def abort():
        raise PipelineAborted("Синхронизацию перехватил другой запуск")

    orch = PipelineOrchestrator(stages=[s1], db=MagicMock(), bus=bus, before_stage=abort)
    result = await orch.run(mode="full", trigger="manual", run_id="r1")

    assert s1.calls == 0
    assert result == {"status": "failed", "stages": [], "error": "Синхронизацию перехватил другой запуск"}
    published = [c.args[0] for c in bus.publish.call_args_list]
    assert published[-1] == {"type": "pipeline_done", "run_id": "r1", "status": "failed"}
