"""WorkTypeClusterer — Cluster-фаза: группировка candidate_name в темы."""
import pytest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import AsyncMock

from app.services.llm.work_type_clusterer import (
    WorkTypeClusterer, build_cluster_prompt,
)


@dataclass
class _FakeCls:
    """Minimal stub — mirrors the fields WorkTypeClusterer reads from IssueClassification."""
    issue_id: str
    candidate_name: Optional[str]
    theme_id: Optional[str] = None
    failed: bool = False


def _make_cls(issue_id: str, candidate_name: str) -> _FakeCls:
    return _FakeCls(issue_id=issue_id, candidate_name=candidate_name)


@pytest.mark.asyncio
async def test_cluster_empty_returns_empty():
    provider = AsyncMock()
    clusterer = WorkTypeClusterer(provider=provider)
    result = await clusterer.cluster([])
    assert result == {}
    provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_single_candidate_returns_empty():
    provider = AsyncMock()
    clusterer = WorkTypeClusterer(provider=provider)
    result = await clusterer.cluster([_make_cls("i1", "Ошибки обмена")])
    assert result == {}
    provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_five_candidates_two_clusters():
    """5 кандидатов → 2 кластера из fake LLM → корректный маппинг."""
    names = ["Ошибки обмена", "Сбои интеграции", "Доработка отчётов", "Проводки", "Ошибки НСИ"]
    classifications = [_make_cls(f"i{i}", n) for i, n in enumerate(names)]

    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(return_value=(
        {
            "clusters": [
                {"name": "Ошибки и сбои", "candidate_names": ["Ошибки обмена", "Сбои интеграции", "Ошибки НСИ"]},
                {"name": "Учёт и отчётность", "candidate_names": ["Доработка отчётов", "Проводки"]},
            ]
        },
        {"model": "test-model"},
    ))

    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(classifications)

    assert mapping["Ошибки обмена"] == "Ошибки и сбои"
    assert mapping["Сбои интеграции"] == "Ошибки и сбои"
    assert mapping["Ошибки НСИ"] == "Ошибки и сбои"
    assert mapping["Доработка отчётов"] == "Учёт и отчётность"
    assert mapping["Проводки"] == "Учёт и отчётность"
    fake_provider.cluster_candidates.assert_called_once()


@pytest.mark.asyncio
async def test_cluster_provider_exception_returns_identity():
    """При ошибке LLM возвращает identity-mapping (каждый кандидат = сам себе кластер)."""
    names = ["Ошибки обмена", "Сбои интеграции", "Доработка отчётов"]
    classifications = [_make_cls(f"i{i}", n) for i, n in enumerate(names)]

    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(classifications)

    # Identity mapping: each candidate maps to itself
    for name in names:
        assert mapping[name] == name


@pytest.mark.asyncio
async def test_cluster_prompt_contains_all_candidates_and_counts():
    """Промпт включает все candidate_name, часы и кол-во задач."""
    names = ["Ошибки обмена", "Доработка отчётов"]
    classifications = [_make_cls(f"i{i}", n) for i, n in enumerate(names)]

    captured_prompt: list[str] = []

    async def mock_cluster(prompt: str) -> tuple[dict, dict]:
        captured_prompt.append(prompt)
        return (
            {
                "clusters": [
                    {"name": "Всё", "candidate_names": names},
                ]
            },
            {"model": "test"},
        )

    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = mock_cluster

    hours_by_issue = {"i0": 10.5, "i1": 5.0}
    key_by_issue = {"i0": "PROJ-1", "i1": "PROJ-2"}

    clusterer = WorkTypeClusterer(provider=fake_provider)
    await clusterer.cluster(classifications, hours_by_issue=hours_by_issue, key_by_issue=key_by_issue)

    assert len(captured_prompt) == 1
    prompt = captured_prompt[0]
    assert "Ошибки обмена" in prompt
    assert "Доработка отчётов" in prompt
    assert "10.5" in prompt
    assert "5.0" in prompt
    assert "1 задач" in prompt  # count = 1 each
    assert "PROJ-1" in prompt
    assert "PROJ-2" in prompt


@pytest.mark.asyncio
async def test_cluster_uncovered_candidate_keeps_own_name():
    """Если LLM не включил candidate_name в ни один кластер — он остаётся сам собой."""
    names = ["А", "Б", "В"]
    classifications = [_make_cls(f"i{i}", n) for i, n in enumerate(names)]

    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(return_value=(
        {
            "clusters": [
                # "В" не попал ни в один кластер
                {"name": "АБ", "candidate_names": ["А", "Б"]},
            ]
        },
        {"model": "test"},
    ))

    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(classifications)

    assert mapping["А"] == "АБ"
    assert mapping["Б"] == "АБ"
    assert mapping["В"] == "В"  # identity fallback


def test_build_cluster_prompt_structure():
    """Промпт содержит ключевые инструкции."""
    candidates = [
        {"candidate_name": "Ошибки", "hours": 10.0, "count": 3, "sample_keys": ["P-1"]},
        {"candidate_name": "Отчёты", "hours": 5.0, "count": 2, "sample_keys": []},
    ]
    prompt = build_cluster_prompt(candidates)
    assert "РОВНО В ОДИН кластер" in prompt
    assert "Ошибки" in prompt
    assert "Отчёты" in prompt
    assert "10.0" in prompt
    assert "5.0" in prompt
    assert "P-1" in prompt
    assert "clusters" in prompt  # JSON schema hint
