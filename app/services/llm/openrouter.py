"""OpenRouter provider — десятки моделей через единый OpenAI-compat API.

Endpoint: https://openrouter.ai/api/v1/chat/completions
Free models: суффикс ":free" в id (deepseek-chat, llama, qwen, gemma и др.).
Free tier: ~20 RPM / 50 RPD на ключ (общая квота для всех :free моделей).
"""
import json
import logging
from typing import Any

import httpx

from app.services.llm.gemini import GEMINI_RESPONSE_SCHEMA
from app.services.llm.types import ProjectSummary


logger = logging.getLogger("jira_analytics.llm")


_DEFAULT_MODEL = "deepseek/deepseek-chat-v3.1:free"
_BASE_URL = "https://openrouter.ai/api/v1"
_REFERER = "http://localhost"
_TITLE = "JiraAnalysis"


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.model = model

    async def summarize_project(self, prompt: str, *, expect_json: bool = True) -> tuple[ProjectSummary, dict]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if expect_json:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "project_summary",
                    "strict": True,
                    "schema": GEMINI_RESPONSE_SCHEMA,
                },
            }

        resp = await self._post(f"{_BASE_URL}/chat/completions", body)
        text = resp["choices"][0]["message"]["content"]
        data = json.loads(text)

        usage = resp.get("usage", {}) or {}
        meta = {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "model": self.model,
        }
        return ProjectSummary.model_validate(data), meta

    async def healthcheck(self) -> bool:
        try:
            await self._post(
                f"{_BASE_URL}/chat/completions",
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            return True
        except Exception as e:
            logger.warning("OpenRouter healthcheck failed: %s", e)
            return False

    async def _post(self, url: str, body: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": _REFERER,
            "X-Title": _TITLE,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
