"""GeminiProvider — структурированный JSON ответ через httpx-мок."""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm.gemini import GeminiProvider
from app.services.llm.types import ProjectSummary


@pytest.mark.asyncio
async def test_summarize_returns_parsed_summary():
    provider = GeminiProvider(api_key="fake")
    fake_resp = {
        "candidates": [{
            "content": {"parts": [{"text":
                '{"goals":["g1","g2","g3"],'
                '"result_checklist":[{"label":"x","done":true,"category":"analysis"}],'
                '"status_text":"OK","workload_summary":"WS",'
                '"work_breakdown":[{"bucket":"analysis","label":"Анализ","child_keys":["A-1"]}]}'
            }]},
        }],
        "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50},
    }
    with patch.object(provider, "_post", AsyncMock(return_value=fake_resp)):
        summary, meta = await provider.summarize_project("test prompt")

    assert isinstance(summary, ProjectSummary)
    assert summary.goals == ["g1", "g2", "g3"]
    assert summary.result_checklist[0].category == "analysis"
    assert summary.work_breakdown[0].bucket == "analysis"
    assert meta["input_tokens"] == 100
    assert meta["output_tokens"] == 50
    assert meta["model"] == "gemini-2.0-flash"


@pytest.mark.asyncio
async def test_healthcheck_returns_true_on_success():
    provider = GeminiProvider(api_key="fake")
    with patch.object(provider, "_post", AsyncMock(return_value={"candidates": []})):
        assert await provider.healthcheck() is True


@pytest.mark.asyncio
async def test_healthcheck_returns_false_on_error():
    provider = GeminiProvider(api_key="fake")
    with patch.object(provider, "_post", AsyncMock(side_effect=Exception("boom"))):
        assert await provider.healthcheck() is False
