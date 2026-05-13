"""Tests for EmbeddingMatcher cosine-based theme search."""
import pytest

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.services.llm.embedding_matcher import EmbeddingMatcher
from app.services.llm.embedding_service import EmbeddingService
from app.services.llm.theme_embedding_service import ThemeEmbeddingService


@pytest.fixture
def work_type(db_session):
    wt = MandatoryWorkType(
        code="test_wt_match",
        label="Test match",
        is_active=True,
        sort_order=0,
    )
    db_session.add(wt)
    db_session.commit()
    return wt


def test_find_best_theme_returns_match_above_threshold(db_session, work_type):
    t1 = Theme(
        work_type_id=work_type.id,
        name="Себестоимость",
        description="Расчёт себестоимости товаров",
    )
    t2 = Theme(
        work_type_id=work_type.id,
        name="Права доступа",
        description="Настройка прав, ролей пользователей",
    )
    db_session.add_all([t1, t2])
    db_session.commit()

    tes = ThemeEmbeddingService(db_session)
    tes.recompute_theme_embedding(t1.id)
    tes.recompute_theme_embedding(t2.id)
    db_session.refresh(t1)
    db_session.refresh(t2)

    embedder = EmbeddingService()
    issue_vec = embedder.encode_text(
        "Расчёт таможенной стоимости импорта",
        kind="query",
    )

    matcher = EmbeddingMatcher(tes)
    best, score = matcher.find_best_theme(issue_vec, [t1, t2], threshold=0.5)
    assert best is not None
    assert best.id == t1.id
    assert score > 0.5


def test_find_best_returns_none_below_threshold(db_session, work_type):
    t = Theme(
        work_type_id=work_type.id,
        name="Бухгалтерия",
        description="Учёт операций",
    )
    db_session.add(t)
    db_session.commit()

    tes = ThemeEmbeddingService(db_session)
    tes.recompute_theme_embedding(t.id)
    db_session.refresh(t)

    issue_vec = EmbeddingService().encode_text(
        "Совершенно несвязанная тема про космос",
        kind="query",
    )
    matcher = EmbeddingMatcher(tes)
    best, _score = matcher.find_best_theme(issue_vec, [t], threshold=0.95)
    assert best is None


def test_lazy_recompute_when_theme_has_no_vector(db_session, work_type):
    t = Theme(
        work_type_id=work_type.id,
        name="Себестоимость",
        description="Расчёт себестоимости",
    )
    db_session.add(t)
    db_session.commit()
    # Embedding не считаем — должен быть None.
    assert t.embedding is None

    embedder = EmbeddingService()
    issue_vec = embedder.encode_text("Себестоимость товаров", kind="query")

    tes = ThemeEmbeddingService(db_session)
    matcher = EmbeddingMatcher(tes)
    best, score = matcher.find_best_theme(issue_vec, [t], threshold=0.3)
    assert best is not None
    assert score > 0.3
    # Lazy recompute должен был записать embedding.
    db_session.refresh(t)
    assert t.embedding is not None
