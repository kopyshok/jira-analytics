"""Provider-level Gemini tests: classify_issue + cluster_candidates new contract."""
import json
import re
import httpx
import pytest
import respx

from app.services.llm.gemini import GeminiProvider
from app.services.llm.work_type_classifier import ClassificationResult


_GEMINI_URL_RE = re.compile(
    r"https://generativelanguage\.googleapis\.com/v1beta/models/.*:generateContent.*"
)


def _gemini_response(payload: dict, status: int = 200) -> httpx.Response:
    body = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
        "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
    }
    return httpx.Response(status, json=body)


@pytest.mark.asyncio
@respx.mock
async def test_gemini_classify_issue_emits_markers_area_nature():
    respx.post(url__regex=_GEMINI_URL_RE).mock(
        return_value=_gemini_response({
            "theme_id": "T1",
            "candidate_name": None,
            "contribution_text": "разбор сбоев",
            "confidence": 0.85,
            "markers": ["Obmen Dannyh", "  integraciya_erp  ", "", "korrekcia_dannyh"],
            "area": "обмен_данных",
            "nature": "integration",
        })
    )
    p = GeminiProvider(api_key="k", model="gemini-2.0-flash")
    res, meta = await p.classify_issue(
        "prompt", [{"id": "T1", "name": "X", "description": None}]
    )
    assert isinstance(res, ClassificationResult)
    assert res.theme_id == "T1"
    assert res.confidence == 0.85
    # нормализация: lowercase, strip, spaces->underscores; пустые отброшены
    assert res.markers == ["obmen_dannyh", "integraciya_erp", "korrekcia_dannyh"]
    assert res.area == "обмен_данных"
    assert res.nature == "integration"
    assert meta.get("model") == "gemini-2.0-flash"


@pytest.mark.asyncio
@respx.mock
async def test_gemini_classify_invalid_nature_becomes_none():
    respx.post(url__regex=_GEMINI_URL_RE).mock(
        return_value=_gemini_response({
            "theme_id": None,
            "candidate_name": "Новая",
            "contribution_text": None,
            "confidence": 0.5,
            "markers": [],
            "area": None,
            "nature": "made-up-value",
        })
    )
    p = GeminiProvider(api_key="k")
    res, _ = await p.classify_issue("prompt", [])
    assert res.nature is None
    assert res.markers == []
    assert res.area is None


@pytest.mark.asyncio
@respx.mock
async def test_gemini_classify_markers_capped_at_8():
    respx.post(url__regex=_GEMINI_URL_RE).mock(
        return_value=_gemini_response({
            "theme_id": None,
            "candidate_name": None,
            "contribution_text": None,
            "confidence": 0.3,
            "markers": [f"m{i}" for i in range(20)],
            "area": "x",
            "nature": "other",
        })
    )
    p = GeminiProvider(api_key="k")
    res, _ = await p.classify_issue("prompt", [])
    assert len(res.markers) == 8
    assert res.markers == [f"m{i}" for i in range(8)]


@pytest.mark.asyncio
@respx.mock
async def test_gemini_cluster_candidates_returns_markers():
    expected = {
        "clusters": [
            {"name": "Обмены данными", "markers": ["obmen_dannyh", "integraciya_erp"]},
            {"name": "Закрытие периода", "markers": ["zakrytie_perioda"]},
        ]
    }
    respx.post(url__regex=_GEMINI_URL_RE).mock(
        return_value=_gemini_response(expected)
    )
    p = GeminiProvider(api_key="k")
    data, meta = await p.cluster_candidates("prompt")
    assert "clusters" in data
    assert data["clusters"][0]["markers"] == ["obmen_dannyh", "integraciya_erp"]
    assert data["clusters"][0]["name"] == "Обмены данными"
    assert meta.get("model") == "gemini-2.0-flash"
