"""ExecutiveSynthesizer tests."""
from unittest.mock import AsyncMock

import pytest

from app.services.llm.executive_synthesizer import (
    ExecutiveSynthesizer,
    build_executive_prompt,
)


@pytest.mark.asyncio
async def test_synthesizer_happy_path():
    provider = AsyncMock()
    provider.model = "test"
    provider.synthesize_executive_summary = AsyncMock(return_value=(
        {"improved": "SLA вырос", "risk": "Очередь растёт", "action": "Усилить 1ю линию"},
        {"model": "test"},
    ))
    s = ExecutiveSynthesizer(provider)
    out, _meta = await s.synthesize({"kpi": {"health_index": 80}})
    assert out.improved == "SLA вырос"
    assert out.risk == "Очередь растёт"
    assert out.action == "Усилить 1ю линию"
    assert not out.is_fallback


@pytest.mark.asyncio
async def test_synthesizer_provider_failure_falls_back():
    provider = AsyncMock()
    provider.model = "test"
    provider.synthesize_executive_summary = AsyncMock(side_effect=RuntimeError("boom"))
    s = ExecutiveSynthesizer(provider)
    out, _meta = await s.synthesize({"kpi": {"health_index": 60, "critical_risks_count": 3}})
    assert out.is_fallback
    assert "60" in out.improved
    assert "3" in out.risk


@pytest.mark.asyncio
async def test_synthesizer_incomplete_output_falls_back():
    provider = AsyncMock()
    provider.model = "test"
    provider.synthesize_executive_summary = AsyncMock(return_value=(
        {"improved": "ok", "risk": "", "action": "do"}, {"model": "test"},
    ))
    s = ExecutiveSynthesizer(provider)
    out, _ = await s.synthesize({"kpi": {}})
    assert out.is_fallback


def test_prompt_contains_findings():
    prompt = build_executive_prompt({"kpi": {"health_index": 86}, "modules": []})
    assert "86" in prompt
    assert "improved" in prompt
    assert "risk" in prompt
    assert "action" in prompt
