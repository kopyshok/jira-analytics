"""Tests for ThemeEmbeddingService centroid computation."""
import numpy as np
import pytest

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.services.llm.embedding_service import EMBEDDING_DIM, MODEL_VERSION
from app.services.llm.theme_embedding_service import ThemeEmbeddingService


@pytest.fixture
def work_type(db_session):
    wt = MandatoryWorkType(
        code="test_wt_embed",
        label="Test embed",
        is_active=True,
        sort_order=0,
    )
    db_session.add(wt)
    db_session.commit()
    return wt


def test_compute_theme_embedding_no_issues_text_only(db_session, work_type):
    theme = Theme(
        work_type_id=work_type.id,
        name="Расчёт и анализ себестоимости",
        description="Себестоимость товаров и услуг",
    )
    theme.aliases = ["Таможенная стоимость", "Корректировка стоимости"]
    db_session.add(theme)
    db_session.commit()

    svc = ThemeEmbeddingService(db_session)
    vec = svc.compute_theme_embedding(theme, top_issues=[])
    assert vec.shape == (EMBEDDING_DIM,)
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-3


def test_recompute_persists_to_theme(db_session, work_type):
    theme = Theme(
        work_type_id=work_type.id,
        name="Закрытие периода",
        description=None,
    )
    db_session.add(theme)
    db_session.commit()

    svc = ThemeEmbeddingService(db_session)
    svc.recompute_theme_embedding(theme.id)

    db_session.refresh(theme)
    assert theme.embedding is not None
    assert theme.embedding_model_version == MODEL_VERSION
    assert theme.embedding_updated_at is not None


def test_load_vector_roundtrip(db_session, work_type):
    theme = Theme(work_type_id=work_type.id, name="X", description="y")
    db_session.add(theme)
    db_session.commit()

    svc = ThemeEmbeddingService(db_session)
    svc.recompute_theme_embedding(theme.id)
    db_session.refresh(theme)

    vec = svc.load_vector(theme)
    assert vec is not None
    assert vec.shape == (EMBEDDING_DIM,)
    assert abs(float(np.linalg.norm(vec)) - 1.0) < 1e-3


def test_load_vector_returns_none_on_wrong_model(db_session, work_type):
    theme = Theme(work_type_id=work_type.id, name="X", description="y")
    db_session.add(theme)
    db_session.commit()

    svc = ThemeEmbeddingService(db_session)
    svc.recompute_theme_embedding(theme.id)
    db_session.refresh(theme)

    theme.embedding_model_version = "stale-version"
    db_session.commit()
    db_session.refresh(theme)

    assert svc.load_vector(theme) is None


def test_text_for_theme_includes_aliases(db_session, work_type):
    theme = Theme(
        work_type_id=work_type.id,
        name="Себестоимость",
        description="Описание",
    )
    theme.aliases = ["Таможня"]
    db_session.add(theme)
    db_session.commit()

    svc = ThemeEmbeddingService(db_session)
    text = svc._theme_text(theme)
    assert "Себестоимость" in text
    assert "Описание" in text
    assert "Таможня" in text
