"""Tests for EmbeddingService singleton."""
import numpy as np
import pytest

from app.services.llm.embedding_service import (
    EMBEDDING_DIM,
    MODEL_VERSION,
    EmbeddingService,
)


@pytest.fixture(scope="module")
def svc() -> EmbeddingService:
    return EmbeddingService()


def test_encode_text_returns_normalized_768(svc: EmbeddingService) -> None:
    v = svc.encode_text("Расчёт себестоимости товара")
    assert v.shape == (EMBEDDING_DIM,)
    assert v.dtype == np.float32
    norm = float(np.linalg.norm(v))
    assert abs(norm - 1.0) < 1e-3


def test_encode_batch_returns_matrix(svc: EmbeddingService) -> None:
    vs = svc.encode_batch(["а", "б", "в"])
    assert vs.shape == (3, EMBEDDING_DIM)
    norms = np.linalg.norm(vs, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-3)


def test_model_version_const() -> None:
    assert isinstance(MODEL_VERSION, str)
    assert MODEL_VERSION.startswith("e5-base-")


def test_semantic_similarity(svc: EmbeddingService) -> None:
    """Близкие по смыслу тексты должны иметь cosine ≥ 0.7."""
    a = svc.encode_text("Расчёт себестоимости товара")
    b = svc.encode_text("Анализ себестоимости продукции")
    c = svc.encode_text("Настройка прав доступа")
    sim_ab = float(np.dot(a, b))
    sim_ac = float(np.dot(a, c))
    assert sim_ab > 0.7
    assert sim_ab > sim_ac


def test_singleton_identity() -> None:
    a = EmbeddingService()
    b = EmbeddingService()
    assert a is b
