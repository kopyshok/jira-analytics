"""Google Gemini 2.0 Flash через AI Studio API.

Endpoint: https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
Free tier: 15 RPM, 1M токенов/день.
"""
import json
import logging
from typing import Any

import httpx

from app.services.llm.types import ProjectSummary


logger = logging.getLogger("jira_analytics.llm")


_BUCKETS = ["analysis", "development", "testing", "ope"]


GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "goals": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        "result_checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "done": {"type": "boolean"},
                    "category": {"type": "string", "enum": _BUCKETS},
                },
                "required": ["label", "done", "category"],
            },
            "minItems": 0, "maxItems": 8,
        },
        "status_text": {"type": "string"},
        "workload_summary": {"type": "string"},
        "work_breakdown": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bucket": {"type": "string", "enum": _BUCKETS},
                    "label": {"type": "string"},
                    "child_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 50,
                    },
                },
                "required": ["bucket", "label", "child_keys"],
            },
            "minItems": 1,
            "maxItems": 8,
        },
    },
    "required": ["goals", "result_checklist", "status_text", "workload_summary", "work_breakdown"],
}


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model
        self.last_error: str | None = None
        self._base = "https://generativelanguage.googleapis.com/v1beta/models"

    async def summarize_project(self, prompt: str, *, expect_json: bool = True) -> tuple[ProjectSummary, dict]:
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
        if expect_json:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = GEMINI_RESPONSE_SCHEMA

        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)

        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)

        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
        return ProjectSummary.model_validate(data), meta

    async def healthcheck(self) -> bool:
        """Минимальный prompt 'ping' — проверка ключа и соединения."""
        self.last_error = None
        try:
            url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
            await self._post(url, {"contents": [{"parts": [{"text": "ping"}]}]})
            return True
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            self.last_error = f"HTTP {e.response.status_code}: {body}"
            logger.warning("Gemini healthcheck failed: %s", self.last_error)
            return False
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            logger.warning("Gemini healthcheck failed: %s", self.last_error)
            return False

    async def _post(self, url: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json()
