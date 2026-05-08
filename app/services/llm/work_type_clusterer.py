"""Cluster-фаза тематического отчёта: группировка raw candidate_name в N=5..15 тем.

Запускается ПОСЛЕ Map-фазы для записей с theme_id IS NULL AND failed=False AND candidate_name IS NOT NULL.
Результат: перезаписывает candidate_name на имя кластера.
"""
import logging
from dataclasses import dataclass
from typing import Protocol

from app.models.issue_classification import IssueClassification


logger = logging.getLogger("jira_analytics.thematic")
PROMPT_VERSION = "wt-cluster-v1"


@dataclass
class Cluster:
    name: str
    candidate_names: list[str]


@dataclass
class ClusterResult:
    clusters: list[Cluster]


class ClustererProvider(Protocol):
    model: str

    async def cluster_candidates(self, prompt: str) -> tuple[dict, dict]: ...


def build_cluster_prompt(candidates: list[dict]) -> str:
    """Промпт Cluster-фазы.

    candidates — список dict с ключами: candidate_name, hours, count, sample_keys.
    Просит LLM сгруппировать candidate_name в 5-15 кластеров с краткими
    русскоязычными названиями (3-7 слов). Каждое имя должно попасть ровно в
    один кластер — без пропусков и дублей.
    """
    lines = [
        "Ты — аналитик. Ниже список предложенных названий тем задач сопровождения.",
        "Задача: сгруппируй их в 5-15 широких категорий-кластеров.",
        "",
        "Правила:",
        "- Название каждого кластера — краткое (3-7 слов), на русском языке.",
        "- Каждое candidate_name из входного списка должно войти РОВНО В ОДИН кластер.",
        "- Не пропускай ни одно candidate_name из входного списка.",
        "- Не выдумывай candidate_name, которых нет во входном списке.",
        "- Кластеры — широкие категории, не описания конкретных задач.",
        "- Не упоминай ФИО и конкретные имена систем там, где это не нужно.",
        "",
        "Входные данные (candidate_name | часы | кол-во задач | примеры ключей Jira):",
    ]
    for c in candidates:
        sample = ", ".join(c.get("sample_keys") or [])
        hours_val = c.get("hours")
        hours_str = f"{hours_val}ч | " if hours_val is not None else ""
        lines.append(
            f'- "{c["candidate_name"]}" | {hours_str}{c["count"]} задач'
            + (f" | примеры: {sample}" if sample else "")
        )
    lines.extend([
        "",
        'Верни JSON: {"clusters": [{"name": "...", "candidate_names": ["...", ...]}, ...]}',
    ])
    return "\n".join(lines)


class WorkTypeClusterer:
    """Cluster-фаза. Один LLM-вызов; при ошибке — identity-mapping (каждый candidate остаётся сам собой)."""

    def __init__(self, provider: ClustererProvider) -> None:
        self.provider = provider

    async def cluster(
        self,
        classifications: list[IssueClassification],
        *,
        hours_by_issue: dict[str, float] | None = None,
        key_by_issue: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Возвращает маппинг {candidate_name → cluster_name}.

        Если <2 уникальных candidate_name → возвращает {} (кластеризация не нужна).
        При ошибке LLM → возвращает identity-mapping (имя кластера = candidate_name).

        hours_by_issue: опциональный dict {issue_id → hours} для обогащения промпта.
        key_by_issue:   опциональный dict {issue_id → jira_key} для sample_keys.
        """
        hours_by_issue = hours_by_issue or {}
        key_by_issue = key_by_issue or {}

        # Собираем агрегат по уникальным candidate_name
        agg: dict[str, dict] = {}
        for c in classifications:
            name = c.candidate_name
            if not name:
                continue
            if name not in agg:
                agg[name] = {"candidate_name": name, "hours": 0.0, "count": 0, "sample_keys": []}
            entry = agg[name]
            issue_hours = hours_by_issue.get(c.issue_id, 0.0)
            entry["hours"] += issue_hours
            entry["count"] += 1
            issue_key = key_by_issue.get(c.issue_id)
            if issue_key and len(entry["sample_keys"]) < 5:
                entry["sample_keys"].append(issue_key)

        if len(agg) < 2:
            return {}

        # Round hours for readability
        candidates = [
            {**v, "hours": round(v["hours"], 1)} for v in agg.values()
        ]
        prompt = build_cluster_prompt(candidates)

        identity: dict[str, str] = {name: name for name in agg}

        try:
            obj, meta = await self.provider.cluster_candidates(prompt)
        except Exception as e:
            logger.warning("WorkTypeClusterer: LLM call failed, using identity mapping: %s", e)
            return identity

        raw_clusters = obj.get("clusters") or []
        if not isinstance(raw_clusters, list) or not raw_clusters:
            logger.warning("WorkTypeClusterer: empty/invalid clusters response, using identity mapping")
            return identity

        mapping: dict[str, str] = {}
        for cl in raw_clusters:
            cluster_name = (cl.get("name") or "").strip()
            if not cluster_name:
                continue
            for cand_name in cl.get("candidate_names") or []:
                if isinstance(cand_name, str) and cand_name in agg:
                    mapping[cand_name] = cluster_name

        # Fallback: any candidate not covered by LLM keeps its own name
        for name in agg:
            if name not in mapping:
                logger.debug(
                    "WorkTypeClusterer: candidate '%s' not assigned to any cluster, keeping as-is",
                    name,
                )
                mapping[name] = name

        logger.info(
            "WorkTypeClusterer: %d candidates → %d clusters (model=%s)",
            len(agg),
            len({v for v in mapping.values()}),
            meta.get("model"),
        )
        return mapping
