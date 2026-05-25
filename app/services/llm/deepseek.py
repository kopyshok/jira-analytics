"""DeepSeek provider — прямой API через api.deepseek.com.

Endpoint: https://api.deepseek.com/v1/chat/completions (OpenAI-compat).
Модели:
  - deepseek-chat — V3.2-Exp, general purpose, дешёвый ($0.27/M input)
  - deepseek-reasoner — R1, chain-of-thought, дороже но качество SOTA

Free tier нет (закрыли в 2025). Лимиты: 60 RPM на ключ, без RPD-cap.

Структурный вывод: DeepSeek поддерживает `response_format: {type: "json_object"}`
(не `json_schema`). Промпт сам инструктирует формат; ответ парсим в JSON
руками + валидируем через Pydantic.
"""
import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.services.llm.openrouter import LLMResponseError
from app.services.llm.types import ProjectSummary


logger = logging.getLogger("jira_analytics.llm")


_DEFAULT_MODEL = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.model = model
        self.last_error: str | None = None

    async def summarize_project(
        self, prompt: str, *, expect_json: bool = True,
    ) -> tuple[ProjectSummary, dict]:
        data, meta = await self._call_json(self.model, prompt, json_mode=expect_json)
        try:
            return ProjectSummary.model_validate(data), meta
        except ValidationError as e:
            raise LLMResponseError(f"DeepSeek {self.model} вернул JSON не по схеме: {e}") from e

    async def classify_issue(
        self, prompt: str, themes_payload: list[dict],
    ) -> tuple["ClassificationResult", dict]:
        from app.services.llm.work_type_classifier import ClassificationResult

        nature_enum = [
            "bug", "enhancement", "consultation", "regulatory",
            "data_fix", "integration", "access_request", "other",
        ]
        obj, meta = await self._call_json(self.model, prompt, json_mode=True)
        valid_ids = {t["id"] for t in themes_payload}
        tid = obj.get("theme_id")
        if tid and tid not in valid_ids:
            tid = None
        raw_markers = obj.get("markers") or []
        markers = [
            m.strip().lower().replace(" ", "_")[:60]
            for m in raw_markers
            if isinstance(m, str) and m.strip()
        ][:8]
        nature = obj.get("nature")
        if nature not in nature_enum:
            nature = None
        return ClassificationResult(
            theme_id=tid,
            candidate_name=(obj.get("candidate_name") or "").strip()[:255] or None,
            contribution_text=(obj.get("contribution_text") or "").strip()[:200] or None,
            confidence=float(obj.get("confidence") or 0.0),
            nature_tag=None,
            markers=markers,
            area=(obj.get("area") or "").strip()[:120] or None,
            nature=nature,
        ), meta

    async def cluster_candidates(self, prompt: str) -> tuple[dict, dict]:
        return await self._call_json(self.model, prompt, json_mode=True)

    async def synthesize_work_type_report(self, prompt: str) -> tuple[dict, dict]:
        return await self._call_json(self.model, prompt, json_mode=True)

    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]:
        return await self._call_json(self.model, prompt, json_mode=True)

    async def healthcheck(self) -> bool:
        """GET /models — проверка ключа без расхода токенов."""
        self.last_error = None
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{_BASE_URL}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                r.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            self.last_error = f"HTTP {e.response.status_code}: {body}"
            logger.warning("DeepSeek healthcheck failed: %s", self.last_error)
            return False
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            logger.warning("DeepSeek healthcheck failed: %s", self.last_error)
            return False

    async def _call_json(
        self, model: str, prompt: str, *, json_mode: bool,
    ) -> tuple[dict, dict]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        resp = await self._post(f"{_BASE_URL}/chat/completions", body)
        try:
            text = resp["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseError(
                f"DeepSeek вернул неожиданную структуру ответа ({type(e).__name__}). "
                f"Тело: {str(resp)[:500]}"
            ) from e
        if not text.strip():
            raise LLMResponseError(f"DeepSeek {model} вернул пустой ответ.")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMResponseError(
                f"DeepSeek {model} вернул не-JSON. Первые 300 символов: {text[:300]}"
            ) from e
        usage = resp.get("usage", {}) or {}
        meta = {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "model": model,
        }
        return data, meta

    async def _post(self, url: str, body: dict) -> dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return r.json()
