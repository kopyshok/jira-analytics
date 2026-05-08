"""WorkTypeClusterer — группировка по markers."""
import pytest
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock

from app.services.llm.work_type_clusterer import (
    WorkTypeClusterer, build_cluster_prompt,
)


@dataclass
class _FakeCls:
    issue_id: str
    candidate_name: Optional[str]
    markers: list[str] = field(default_factory=list)
    area: Optional[str] = None
    theme_id: Optional[str] = None
    failed: bool = False


def _make_cls(issue_id: str, candidate_name: str, markers: list[str], area: str = "обмен_данных") -> _FakeCls:
    return _FakeCls(issue_id=issue_id, candidate_name=candidate_name, markers=markers, area=area)


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
    result = await clusterer.cluster([_make_cls("i1", "Ошибки обмена", ["obmen_dannyh"])])
    assert result == {}
    provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_groups_by_marker_overlap():
    """5 кандидатов с разными candidate_name, но общими markers → 2 кластера."""
    cands = [
        _make_cls("i0", "Обмен Розница–ЕРП", ["obmen_dannyh", "integraciya_erp"]),
        _make_cls("i1", "Выгрузка правил УПП", ["obmen_dannyh", "regdannye_nsi"]),
        _make_cls("i2", "Ошибки регистров себестоимости", ["raschet_sebestoimosti", "dvizheniya_registra"]),
        _make_cls("i3", "Корректировка себестоимости металлов", ["raschet_sebestoimosti", "korrekcia_dannyh"]),
        _make_cls("i4", "Обмены передачи товаров", ["obmen_dannyh"]),
    ]

    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(return_value=(
        {
            "clusters": [
                {"name": "Обмены данными", "markers": ["obmen_dannyh", "integraciya_erp", "regdannye_nsi"]},
                {"name": "Себестоимость", "markers": ["raschet_sebestoimosti", "dvizheniya_registra", "korrekcia_dannyh"]},
            ]
        },
        {"model": "test-model"},
    ))

    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)

    assert mapping["Обмен Розница–ЕРП"] == "Обмены данными"
    assert mapping["Выгрузка правил УПП"] == "Обмены данными"
    assert mapping["Обмены передачи товаров"] == "Обмены данными"
    assert mapping["Ошибки регистров себестоимости"] == "Себестоимость"
    assert mapping["Корректировка себестоимости металлов"] == "Себестоимость"


@pytest.mark.asyncio
async def test_cluster_provider_exception_returns_identity():
    """LLM падает → identity mapping."""
    cands = [
        _make_cls("i0", "А", ["m1"]),
        _make_cls("i1", "Б", ["m2"]),
    ]
    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(side_effect=RuntimeError("boom"))
    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)
    assert mapping["А"] == "А"
    assert mapping["Б"] == "Б"


@pytest.mark.asyncio
async def test_cluster_no_markers_returns_identity():
    """Если у всех записей markers пустые → identity mapping (не звать LLM)."""
    cands = [
        _make_cls("i0", "А", []),
        _make_cls("i1", "Б", []),
    ]
    fake_provider = AsyncMock()
    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)
    assert mapping["А"] == "А"
    assert mapping["Б"] == "Б"
    fake_provider.cluster_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_cluster_uncovered_marker_keeps_identity_for_that_candidate():
    """Если LLM не покрыл marker задачи — она остаётся под своим candidate_name."""
    cands = [
        _make_cls("i0", "А", ["m1"]),
        _make_cls("i1", "Б", ["m2"]),
        _make_cls("i2", "В", ["m_unknown"]),
    ]
    fake_provider = AsyncMock()
    fake_provider.cluster_candidates = AsyncMock(return_value=(
        {"clusters": [{"name": "АБ", "markers": ["m1", "m2"]}]},
        {"model": "test"},
    ))
    clusterer = WorkTypeClusterer(provider=fake_provider)
    mapping = await clusterer.cluster(cands)
    assert mapping["А"] == "АБ"
    assert mapping["Б"] == "АБ"
    assert mapping["В"] == "В"


def test_build_cluster_prompt_structure():
    """Промпт содержит markers с частотностью и примерами."""
    prompt = build_cluster_prompt(
        marker_to_examples={
            "m1": ["Тема 1", "Тема 2"],
            "m2": ["Тема 3"],
        },
        marker_freq=Counter({"m1": 5, "m2": 2}),
        target_clusters=3,
    )
    assert "m1 (5 задач)" in prompt
    assert "m2 (2 задач)" in prompt
    assert "Тема 1" in prompt
    assert 'РОВНО В ОДИН кластер' in prompt
    assert "clusters" in prompt
