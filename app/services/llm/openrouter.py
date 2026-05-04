"""OpenRouter provider — десятки моделей через единый OpenAI-compat API.

Endpoint: https://openrouter.ai/api/v1/chat/completions
Free models: суффикс ":free" в id (deepseek-chat, llama, qwen, gemma и др.).
Free tier: ~20 RPM / 50 RPD на ключ (общая квота для всех :free моделей).

Fallback chain: при 429/5xx или некорректном ответе primary-модели
прозрачно пробует следующую из `fallback_models`. Возвращает результат
первой успешной модели и пишет её id в `meta['model']`. Если все упали —
бросает последнюю ошибку.
"""
import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError

from app.services.llm.gemini import GEMINI_RESPONSE_SCHEMA
from app.services.llm.types import ProjectSummary


logger = logging.getLogger("jira_analytics.llm")


class LLMResponseError(Exception):
    """LLM вернул некорректный ответ (пустой, не-JSON, неверная структура)."""


_DEFAULT_MODEL = "qwen/qwen3-next-80b-a3b-instruct:free"

# Цепочка по умолчанию — модели РАЗНЫХ провайдеров. Используется когда
# AppSetting `llm_openrouter_fallback_models` отсутствует (None). Если
# пользователь явно сохранил пустую строку — fallback отключён, остаётся
# только primary.
_DEFAULT_FALLBACK_MODELS = [
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "openai/gpt-oss-120b:free",
    "google/gemma-3-27b-it:free",
    "z-ai/glm-4.5-air:free",
]
_BASE_URL = "https://openrouter.ai/api/v1"
_REFERER = "http://localhost"
_TITLE = "JiraAnalysis"

_RETRY_STATUSES = {429, 500, 502, 503, 504}


class OpenRouterProvider:
    name = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        fallback_models: list[str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        # None → встроенный дефолтный список (RUS-подходящие, разные провайдеры).
        # [] (явный пустой) → fallback отключён, только primary.
        self.fallback_models = (
            list(_DEFAULT_FALLBACK_MODELS) if fallback_models is None else fallback_models
        )
        self.last_error: str | None = None

    async def summarize_project(self, prompt: str, *, expect_json: bool = True) -> tuple[ProjectSummary, dict]:
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for attempt_model in chain:
            try:
                return await self._call_model(attempt_model, prompt, expect_json=expect_json)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    logger.warning(
                        "OpenRouter %s → HTTP %s, fallback к следующей модели",
                        attempt_model, e.response.status_code,
                    )
                    last_exc = e
                    continue
                raise
            except LLMResponseError as e:
                logger.warning("OpenRouter %s → %s, fallback к следующей модели", attempt_model, e)
                last_exc = e
                continue
            except httpx.TimeoutException as e:
                logger.warning("OpenRouter %s → timeout, fallback к следующей модели", attempt_model)
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("Не удалось вызвать ни одну модель OpenRouter (пустая цепочка)")

    async def _call_model(self, model: str, prompt: str, *, expect_json: bool) -> tuple[ProjectSummary, dict]:
        body: dict[str, Any] = {
            "model": model,
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
        try:
            text = resp["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMResponseError(
                f"OpenRouter вернул неожиданную структуру ответа ({type(e).__name__}). "
                f"Модель {model} могла вернуть пустой ответ или ошибку без HTTP-кода. "
                f"Тело: {str(resp)[:500]}"
            ) from e
        if not text.strip():
            raise LLMResponseError(
                f"Модель {model} вернула пустой ответ. "
                f"Возможно она не поддерживает response_format=json_schema."
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMResponseError(
                f"Модель {model} вернула не-JSON. Возможно она игнорирует response_format. "
                f"Первые 300 символов: {text[:300]}"
            ) from e

        usage = resp.get("usage", {}) or {}
        meta = {
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "model": model,
        }
        try:
            summary = ProjectSummary.model_validate(data)
        except ValidationError as e:
            raise LLMResponseError(
                f"Модель {model} вернула JSON не по схеме: {e}"
            ) from e
        return summary, meta

    async def healthcheck(self) -> bool:
        """Проверяет валидность ключа через `/auth/key` — не тратит квоту модели.

        Реальный generation-вызов жёг бы upstream rate-limit (free-модели часто
        в 429), и проверка падала бы по причинам, не связанным с настройкой.
        """
        self.last_error = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": _REFERER,
            "X-Title": _TITLE,
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(f"{_BASE_URL}/auth/key", headers=headers)
                r.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            body = e.response.text[:500]
            self.last_error = f"HTTP {e.response.status_code}: {body}"
            logger.warning("OpenRouter healthcheck failed: %s", self.last_error)
            return False
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            logger.warning("OpenRouter healthcheck failed: %s", self.last_error)
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
