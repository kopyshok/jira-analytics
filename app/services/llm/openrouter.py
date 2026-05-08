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

    async def _call_json(self, model: str, prompt: str, schema: dict | None = None) -> tuple[dict, dict]:
        """POST /chat/completions с опциональной JSON-схемой → (data_dict, meta).

        Не валидирует содержимое — caller сам разбирает dict.
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "strict": True,
                    "schema": schema,
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
        return data, meta

    async def _call_model(self, model: str, prompt: str, *, expect_json: bool) -> tuple[ProjectSummary, dict]:
        schema = GEMINI_RESPONSE_SCHEMA if expect_json else None
        data, meta = await self._call_json(model, prompt, schema)
        try:
            return ProjectSummary.model_validate(data), meta
        except ValidationError as e:
            raise LLMResponseError(f"Модель {model} вернула JSON не по схеме: {e}") from e

    async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple["ClassificationResult", dict]:
        """Map-фаза тематического отчёта. См. WorkTypeClassifier.

        Возвращает ClassificationResult + meta. Использует fallback-цепочку.
        """
        from app.services.llm.work_type_classifier import ClassificationResult

        nature_enum = [
            "bug", "enhancement", "consultation", "regulatory",
            "data_fix", "integration", "access_request", "other",
        ]
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "theme_id": {"type": ["string", "null"]},
                "candidate_name": {"type": ["string", "null"]},
                "contribution_text": {"type": ["string", "null"], "maxLength": 200},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "markers": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 60},
                    "maxItems": 8,
                },
                "area": {"type": ["string", "null"], "maxLength": 120},
                "nature": {"type": ["string", "null"], "enum": [*nature_enum, None]},
            },
            "required": ["theme_id", "confidence"],
        }
        valid_ids = {t["id"] for t in themes_payload}
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for model_id in chain:
            try:
                obj, meta = await self._call_json(model_id, prompt, schema)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    logger.warning("OpenRouter %s → HTTP %s, fallback", model_id, e.response.status_code)
                    last_exc = e
                    continue
                raise
            except (LLMResponseError, httpx.TimeoutException) as e:
                logger.warning("OpenRouter %s classify_issue → %s, fallback", model_id, e)
                last_exc = e
                continue

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
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("classify_issue: пустая цепочка моделей")

    async def cluster_candidates(self, prompt: str) -> tuple[dict, dict]:
        """Cluster-фаза тематического отчёта. Использует fallback-цепочку."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "clusters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "maxLength": 80},
                            "markers": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["name", "markers"],
                    },
                }
            },
            "required": ["clusters"],
        }
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for model_id in chain:
            try:
                return await self._call_json(model_id, prompt, schema)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    last_exc = e
                    continue
                raise
            except (LLMResponseError, httpx.TimeoutException) as e:
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("cluster_candidates: пустая цепочка моделей")

    async def synthesize_work_type_report(self, prompt: str) -> tuple[dict, dict]:
        """Reduce-фаза. Возвращает сырой JSON-ответ + meta. Validation делает caller."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "headline": {"type": "string", "maxLength": 200},
                "themes_narratives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "theme_id": {"type": ["string", "null"]},
                            "narrative": {"type": "string"},
                            "evidence_keys": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["narrative"],
                    },
                },
                "outliers_explanations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string"},
                            "explanation": {"type": "string"},
                        },
                        "required": ["key", "explanation"],
                    },
                },
                "recommendation": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "expected_impact": {"type": "string"},
                    },
                    "required": ["text", "expected_impact"],
                },
            },
            "required": ["headline", "themes_narratives", "outliers_explanations", "recommendation"],
        }
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for model_id in chain:
            try:
                return await self._call_json(model_id, prompt, schema)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    last_exc = e
                    continue
                raise
            except (LLMResponseError, httpx.TimeoutException) as e:
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("synthesize_work_type_report: пустая цепочка моделей")

    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]:
        """Executive dashboard. JSON со схемой improved/risk/action."""
        schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                "improved": {"type": "string", "maxLength": 600},
                "risk": {"type": "string", "maxLength": 600},
                "action": {"type": "string", "maxLength": 600},
            },
            "required": ["improved", "risk", "action"],
        }
        chain = [self.model] + [m for m in self.fallback_models if m and m != self.model]
        last_exc: Exception | None = None
        for model_id in chain:
            try:
                return await self._call_json(model_id, prompt, schema)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in _RETRY_STATUSES:
                    last_exc = e
                    continue
                raise
            except (LLMResponseError, httpx.TimeoutException) as e:
                last_exc = e
                continue
        if last_exc is not None:
            raise last_exc
        raise LLMResponseError("synthesize_executive_summary: пустая цепочка моделей")

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
