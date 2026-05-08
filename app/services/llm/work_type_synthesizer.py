"""Reduce-фаза тематического отчёта: синтез из агрегированных findings.

LLM не видит сырых описаний/комментов — только агрегаты.
Каждое число и ключ задачи в narrative должны присутствовать в findings
(faithfulness validator). При повторных провалах — шаблонный fallback.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from app.services.llm.faithfulness_validator import validate_synthesis


logger = logging.getLogger("jira_analytics.thematic")
PROMPT_VERSION = "wt-synthesize-v2-entities"


@dataclass
class SynthesisOutput:
    headline: str
    themes_narratives: list[dict] = field(default_factory=list)
    outliers_explanations: list[dict] = field(default_factory=list)
    recommendation: dict = field(default_factory=lambda: {"text": "", "expected_impact": ""})
    is_fallback: bool = False


class SynthesizerProvider(Protocol):
    model: str
    async def synthesize_work_type_report(self, prompt: str) -> tuple[dict, dict]: ...


def build_synthesis_prompt(findings: dict) -> str:
    """findings = {totals, themes:[{id,name,hours,pct,top_tasks,entity_breakdown,...}], outliers:[...]}."""
    return "\n".join([
        "Ты — старший аналитик. Пишешь executive-сводку для PM.",
        "Используй ТОЛЬКО числа и ключи задач из FINDINGS. Не выдумывай.",
        "Никаких сравнений конкретных людей. Никаких ФИО.",
        "Стиль: короткий, фактический. Без воды.",
        "",
        "ВАЖНО про темы и их сущности:",
        "  У каждой темы есть `entity_breakdown` — топ имён собственных (систем, модулей,",
        "  контрагентов и т.п.), извлечённых из задач темы, с долей `share_pct` от часов темы.",
        "  Если в теме есть сущность с `share_pct ≥ 40` — ОБЯЗАТЕЛЬНО подсвети её в narrative",
        "  этой темы (например: «большая часть нагрузки по теме приходится на <name>, <share_pct>%»).",
        "  Если доминирующей сущности нет — не упоминай entity_breakdown вовсе.",
        "  Имена сущностей бери ДОСЛОВНО из entity_breakdown.name, числа — из share_pct.",
        "",
        "FINDINGS:",
        json.dumps(findings, ensure_ascii=False, indent=2),
        "",
        "Верни JSON со схемой:",
        "{",
        '  "headline": str (≤180 chars),',
        '  "themes_narratives": [{theme_id, narrative (≤2 предложения), evidence_keys: [...]}],',
        '  "outliers_explanations": [{key, explanation (1 предложение)}],',
        '  "recommendation": {text (1 действие), expected_impact (оценка эффекта)}',
        "}",
    ])


def _fallback_output(findings: dict) -> SynthesisOutput:
    totals = findings.get("totals", {}) or {}
    return SynthesisOutput(
        headline=(
            f"AI-сводка недоступна. Всего {totals.get('hours', 0)} ч / "
            f"{totals.get('tasks', 0)} задач."
        ),
        themes_narratives=[],
        outliers_explanations=[],
        recommendation={"text": "Просмотрите данные ниже.", "expected_impact": ""},
        is_fallback=True,
    )


class WorkTypeSynthesizer:
    """Reduce-фаза. Один retry на faithfulness fail, потом шаблонный fallback."""

    def __init__(self, provider: SynthesizerProvider) -> None:
        self.provider = provider

    async def synthesize(
        self, findings: dict, *, employee_names: set[str],
    ) -> tuple[SynthesisOutput, dict]:
        prompt = build_synthesis_prompt(findings)
        last_meta: dict = {}
        last_errors: list[str] = []
        for attempt in range(2):
            try:
                obj, meta = await self.provider.synthesize_work_type_report(prompt)
            except Exception as e:
                logger.warning("Synthesizer call failed (attempt %d): %s", attempt + 1, e)
                return _fallback_output(findings), {"failure": str(e)[:200]}

            last_meta = meta
            rep = validate_synthesis(obj, findings, employee_names)
            if rep.ok:
                return SynthesisOutput(
                    headline=obj.get("headline", ""),
                    themes_narratives=obj.get("themes_narratives", []) or [],
                    outliers_explanations=obj.get("outliers_explanations", []) or [],
                    recommendation=obj.get("recommendation",
                                          {"text": "", "expected_impact": ""}),
                ), meta

            last_errors = rep.errors
            logger.warning(
                "Faithfulness failed (attempt %d): %s",
                attempt + 1, rep.errors[:3],
            )
            prompt += f"\n\nPREVIOUS_FAILED_VALIDATION: {rep.errors[:3]}"

        out = _fallback_output(findings)
        return out, {**last_meta, "validation_errors": last_errors[:5]}
