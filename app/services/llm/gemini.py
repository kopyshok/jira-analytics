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


GEMINI_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "goals": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
        "result_flow_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "status": {"type": "string", "enum": ["source", "flow", "done"]},
                },
                "required": ["label", "status"],
            },
            "minItems": 1, "maxItems": 6,
        },
        "result_checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "done": {"type": "boolean"},
                },
                "required": ["label", "done"],
            },
            "minItems": 0, "maxItems": 6,
        },
        "status_text": {"type": "string"},
        "workload_summary": {"type": "string"},
    },
    "required": ["goals", "result_flow_blocks", "result_checklist", "status_text", "workload_summary"],
}


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model
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
        try:
            url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
            await self._post(url, {"contents": [{"parts": [{"text": "ping"}]}]})
            return True
        except Exception as e:
            logger.warning("Gemini healthcheck failed: %s", e)
            return False

    async def _post(self, url: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            return r.json()
