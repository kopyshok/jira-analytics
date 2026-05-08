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

    async def classify_issue(self, prompt: str, themes_payload: list[dict]) -> tuple["ClassificationResult", dict]:
        """Map-фаза тематического отчёта. Gemini без fallback-цепочки — single call."""
        from app.services.llm.work_type_classifier import ClassificationResult

        nature_enum = [
            "bug", "enhancement", "consultation", "regulatory",
            "data_fix", "integration", "access_request", "other",
        ]
        schema = {
            "type": "object",
            "properties": {
                "theme_id": {"type": "string", "nullable": True},
                "candidate_name": {"type": "string", "nullable": True},
                "contribution_text": {"type": "string", "nullable": True},
                "confidence": {"type": "number"},
                "markers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                },
                "area": {"type": "string", "nullable": True},
                "nature": {"type": "string", "enum": nature_enum, "nullable": True},
            },
            "required": ["theme_id", "confidence"],
        }
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        obj = json.loads(text)

        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
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
        """Cluster-фаза тематического отчёта. Gemini single call, без fallback-цепочки."""
        schema = {
            "type": "object",
            "properties": {
                "clusters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
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
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
        return data, meta

    async def synthesize_work_type_report(self, prompt: str) -> tuple[dict, dict]:
        """Reduce-фаза. Возвращает сырой JSON + meta. Validation делает caller."""
        schema = {
            "type": "object",
            "properties": {
                "headline": {"type": "string"},
                "themes_narratives": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "theme_id": {"type": "string", "nullable": True},
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
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)

        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
        return data, meta

    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]:
        """Executive dashboard. JSON со схемой improved/risk/action."""
        schema = {
            "type": "object",
            "properties": {
                "improved": {"type": "string"},
                "risk": {"type": "string"},
                "action": {"type": "string"},
            },
            "required": ["improved", "risk", "action"],
        }
        body: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        }
        url = f"{self._base}/{self.model}:generateContent?key={self.api_key}"
        resp = await self._post(url, body)
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(text)
        meta = {
            "input_tokens": resp.get("usageMetadata", {}).get("promptTokenCount"),
            "output_tokens": resp.get("usageMetadata", {}).get("candidatesTokenCount"),
            "model": self.model,
        }
        return data, meta

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
