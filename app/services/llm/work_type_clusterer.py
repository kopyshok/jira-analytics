"""Cluster-фаза тематического отчёта: группировка по markers/area, не по строкам.

После Map-фазы у каждой записи есть markers (контролируемый словарь). Здесь:
1. Считаем частотность всех markers по выборке.
2. Передаём LLM ТОЛЬКО список топ-markers + примеры candidate_names при них.
3. LLM возвращает {cluster_name → [markers]}.
4. Каждой задаче назначаем кластер по принципу "у которого больше всего пересечений с её markers".

Если LLM падает — fallback: одна задача = один кластер по top-marker.
"""
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from app.models.issue_classification import IssueClassification


logger = logging.getLogger("jira_analytics.thematic")
PROMPT_VERSION = "wt-cluster-v2-markers"


class ClustererProvider(Protocol):
    model: str

    async def cluster_candidates(self, prompt: str) -> tuple[dict, dict]: ...


@dataclass
class _Candidate:
    issue_id: str
    candidate_name: str
    markers: list[str]
    area: str | None
    hours: float
    jira_key: str | None


def build_cluster_prompt(
    *,
    marker_to_examples: dict[str, list[str]],
    marker_freq: Counter,
    target_clusters: int,
) -> str:
    """Промпт: входы — markers + примеры. Выход — {cluster_name → [markers]}.

    marker_to_examples: до 5 candidate_name примеров на каждый marker.
    marker_freq: счётчик задач, в которых встречался marker.
    """
    lines = [
        "Ты — старший аналитик. Тебе дан список markers (контролируемых меток) с примерами тем задач при них.",
        "",
        f"Цель: сгруппировать markers в {target_clusters} широких кластеров и дать каждому короткое русское имя (2-4 слова).",
        "",
        "СТРОГИЕ ПРАВИЛА:",
        "1. Имя кластера: 2-4 слова, на русском, БЕЗ упоминания конкретных систем (УПП, ЕРП, Розница) — обобщай.",
        "2. Имя кластера — это широкая ТЕМА. Например «Обмены данными», «Закрытие периода», «Учёт себестоимости».",
        "3. Каждый marker должен войти РОВНО В ОДИН кластер.",
        "4. Не выдумывай новых markers, не пропускай ни один из списка.",
        "5. Группируй по смыслу markers, ИГНОРИРУЯ фразы из примеров (примеры — для контекста, не для имени).",
        "",
        "Markers (количество задач | примеры тем):",
    ]
    for marker, freq in marker_freq.most_common():
        examples = marker_to_examples.get(marker, [])[:3]
        ex_str = " | ".join(examples) if examples else "—"
        lines.append(f"- {marker} ({freq} задач) — {ex_str}")
    lines.extend([
        "",
        'Верни JSON: {"clusters": [{"name": "<2-4 слова>", "markers": ["m1", "m2", ...]}, ...]}',
        f"Целевое количество кластеров: ~{target_clusters}.",
    ])
    return "\n".join(lines)


class WorkTypeClusterer:
    """Группирует кандидатов по контролируемому словарю markers."""

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

        Алгоритм:
        1. Извлекаем markers с каждой записи.
        2. LLM группирует markers в N кластеров с именами.
        3. Для каждой записи: выбираем кластер с максимальным пересечением её markers.
        4. Маппим candidate_name → cluster_name.
        Fallback при ошибке LLM: identity-mapping.
        """
        hours_by_issue = hours_by_issue or {}
        key_by_issue = key_by_issue or {}

        cands: list[_Candidate] = []
        for c in classifications:
            if not c.candidate_name:
                continue
            cands.append(_Candidate(
                issue_id=c.issue_id,
                candidate_name=c.candidate_name,
                markers=list(c.markers),
                area=c.area,
                hours=hours_by_issue.get(c.issue_id, 0.0),
                jira_key=key_by_issue.get(c.issue_id),
            ))

        if len(cands) < 2:
            return {}

        unique_names = {c.candidate_name for c in cands}
        identity = {n: n for n in unique_names}

        # Соберём markers по частотности и примеры candidate_name на каждый marker
        marker_freq: Counter = Counter()
        marker_to_examples: dict[str, list[str]] = {}
        for cand in cands:
            for m in cand.markers:
                marker_freq[m] += 1
                lst = marker_to_examples.setdefault(m, [])
                if cand.candidate_name not in lst and len(lst) < 5:
                    lst.append(cand.candidate_name)

        if not marker_freq:
            logger.info("WorkTypeClusterer: no markers, returning identity mapping")
            return identity

        target_clusters = max(4, min(12, len(marker_freq) // 3))
        prompt = build_cluster_prompt(
            marker_to_examples=marker_to_examples,
            marker_freq=marker_freq,
            target_clusters=target_clusters,
        )

        try:
            obj, meta = await self.provider.cluster_candidates(prompt)
        except Exception as e:
            logger.warning("WorkTypeClusterer: LLM call failed, identity mapping: %s", e)
            return identity

        raw_clusters = obj.get("clusters") or []
        if not isinstance(raw_clusters, list) or not raw_clusters:
            logger.warning("WorkTypeClusterer: empty clusters, identity mapping")
            return identity

        # Построим marker → cluster_name маппинг
        marker_to_cluster: dict[str, str] = {}
        for cl in raw_clusters:
            cluster_name = (cl.get("name") or "").strip()
            if not cluster_name:
                continue
            for m in cl.get("markers") or []:
                if isinstance(m, str) and m in marker_freq:
                    marker_to_cluster[m] = cluster_name

        # Для каждого candidate_name выбираем кластер с максимумом голосов от его markers
        # (агрегируем по уникальным candidate_name, т.к. один candidate_name может встретиться в N задачах
        # с разными markers — берём маркеры всех его задач)
        cand_markers: dict[str, Counter] = {}
        for cand in cands:
            counter = cand_markers.setdefault(cand.candidate_name, Counter())
            for m in cand.markers:
                counter[m] += 1

        mapping: dict[str, str] = {}
        for name, marker_counter in cand_markers.items():
            cluster_votes: Counter = Counter()
            for m, freq in marker_counter.items():
                cn = marker_to_cluster.get(m)
                if cn:
                    cluster_votes[cn] += freq
            if cluster_votes:
                mapping[name] = cluster_votes.most_common(1)[0][0]
            else:
                mapping[name] = name  # fallback identity

        n_clusters = len({v for v in mapping.values()})
        logger.info(
            "WorkTypeClusterer: %d candidates → %d clusters via %d markers (model=%s)",
            len(cand_markers), n_clusters, len(marker_freq), meta.get("model"),
        )
        if n_clusters >= len(cand_markers) * 0.7:
            logger.warning(
                "WorkTypeClusterer: %d clusters from %d candidates (>=70%%) — markers may be too task-specific.",
                n_clusters, len(cand_markers),
            )
        return mapping
