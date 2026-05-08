"""ExecutiveSynthesizer — Reduce-фаза для дашборда руководителя.

3 секции: improved (зелёная), risk (жёлтая), action (серая).
Faithfulness-проверка не такая строгая как в WorkTypeSynthesizer (нет ФИО/ключей задач
в обязательном выводе), но всё равно валидируем JSON структуру.
"""
import json
import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("jira_analytics.executive")
PROMPT_VERSION = "exec-synth-v1"


@dataclass
class ExecutiveSynthesis:
    improved: str
    risk: str
    action: str
    is_fallback: bool = False


class ExecutiveSynthesizerProvider(Protocol):
    model: str

    async def synthesize_executive_summary(self, prompt: str) -> tuple[dict, dict]: ...


def build_executive_prompt(findings: dict) -> str:
    return "\n".join([
        "Ты — старший аналитик службы сопровождения 1С. Готовишь короткую сводку для руководителя.",
        "Используй ТОЛЬКО переданные числа и факты. Не выдумывай.",
        "Никаких ФИО. Никаких сравнений конкретных людей.",
        "Стиль: деловой, фактический, без воды. На русском.",
        "",
        "FINDINGS:",
        json.dumps(findings, ensure_ascii=False, indent=2),
        "",
        "Верни JSON со схемой:",
        "{",
        '  "improved": "<2-3 предложения о том, что улучшилось за период>",',
        '  "risk": "<2-3 предложения о ключевом риске сейчас>",',
        '  "action": "<2-3 предложения о конкретном действии на ближайшие 1-2 недели>"',
        "}",
        "Каждая секция — самостоятельная, без отсылок к другим секциям.",
    ])


def _fallback(findings: dict) -> ExecutiveSynthesis:
    kpi = findings.get("kpi") or {}
    return ExecutiveSynthesis(
        improved=f"Индекс здоровья: {kpi.get('health_index', '—')}/100. AI-сводка недоступна.",
        risk=f"Критичных рисков: {kpi.get('critical_risks_count', 0)}.",
        action="Просмотрите блоки дашборда вручную.",
        is_fallback=True,
    )


class ExecutiveSynthesizer:
    def __init__(self, provider: ExecutiveSynthesizerProvider) -> None:
        self.provider = provider

    async def synthesize(self, findings: dict) -> tuple[ExecutiveSynthesis, dict]:
        prompt = build_executive_prompt(findings)
        try:
            obj, meta = await self.provider.synthesize_executive_summary(prompt)
        except Exception as e:
            logger.warning("ExecutiveSynthesizer failed: %s", e)
            return _fallback(findings), {"failure": str(e)[:200]}

        improved = (obj.get("improved") or "").strip()
        risk = (obj.get("risk") or "").strip()
        action = (obj.get("action") or "").strip()

        if not (improved and risk and action):
            logger.warning("ExecutiveSynthesizer: incomplete output, fallback")
            return _fallback(findings), {**meta, "incomplete": True}

        return ExecutiveSynthesis(improved=improved, risk=risk, action=action), meta
