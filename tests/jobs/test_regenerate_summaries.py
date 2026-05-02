"""Smoke-тест: job возвращает dict со всеми ожидаемыми ключами."""
import pytest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.jobs.regenerate_summaries import regenerate_outdated_summaries


@pytest.fixture
def empty_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_returns_zero_when_no_quarterly_epics(empty_db_session):
    """Пустая БД → processed=0, все ключи присутствуют."""
    # Мокируем SessionLocal чтобы job использовал тестовую сессию
    mock_session_local = MagicMock(return_value=empty_db_session)
    # close() не должен закрывать нашу сессию (она управляется фикстурой)
    empty_db_session.close = MagicMock()

    with patch("app.jobs.regenerate_summaries.SessionLocal", mock_session_local):
        result = await regenerate_outdated_summaries()

    assert result["processed"] == 0
    assert "regenerated" in result
    assert "skipped" in result
    assert "errors" in result
