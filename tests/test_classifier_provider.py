"""Provider-level classify_issue: parsing + fallback + invalid theme_id handling."""
import json
import httpx
import pytest
import respx

from app.services.llm.openrouter import OpenRouterProvider
from app.services.llm.work_type_classifier import ClassificationResult


def _or_response(payload: dict, status: int = 200, model: str = "test-model") -> httpx.Response:
    body = {
        "choices": [{"message": {"content": json.dumps(payload)}}],
        "model": model,
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    return httpx.Response(status, json=body)


@pytest.mark.asyncio
@respx.mock
async def test_or_valid_theme_id_passes_through():
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=_or_response({
            "theme_id": "T1", "candidate_name": None,
            "contribution_text": "x", "confidence": 0.9,
        })
    )
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=[])
    res, meta = await p.classify_issue(
        "prompt", [{"id": "T1", "name": "X", "description": None}]
    )
    assert res.theme_id == "T1"
    assert res.confidence == 0.9
    assert isinstance(res, ClassificationResult)


@pytest.mark.asyncio
@respx.mock
async def test_or_invalid_theme_id_becomes_null():
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=_or_response({
            "theme_id": "ZZZ-not-in-payload", "candidate_name": "Новая тема",
            "contribution_text": "y", "confidence": 0.5,
        })
    )
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=[])
    res, _ = await p.classify_issue(
        "prompt", [{"id": "T1", "name": "X", "description": None}]
    )
    assert res.theme_id is None
    assert res.candidate_name == "Новая тема"


@pytest.mark.asyncio
@respx.mock
async def test_or_429_falls_back_to_second_model():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions")
    route.side_effect = [
        httpx.Response(429, json={"error": "rate"}),
        _or_response(
            {"theme_id": None, "candidate_name": None,
             "contribution_text": "ok", "confidence": 0.5},
            model="m2",
        ),
    ]
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=["m2"])
    res, meta = await p.classify_issue("prompt", [])
    assert res.contribution_text == "ok"
    assert meta.get("model") == "m2"


@pytest.mark.asyncio
@respx.mock
async def test_or_synthesize_returns_dict_unchanged():
    expected = {
        "headline": "test", "themes_narratives": [],
        "outliers_explanations": [],
        "recommendation": {"text": "r", "expected_impact": "i"},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=_or_response(expected)
    )
    p = OpenRouterProvider(api_key="k", model="m1", fallback_models=[])
    obj, meta = await p.synthesize_work_type_report("prompt")
    assert obj == expected
    assert meta.get("model") == "m1"
