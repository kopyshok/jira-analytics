"""Test configuration and fixtures."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.config import Settings

# Ensure ALL models are registered with Base.metadata before create_all().
# The engine fixture is session-scoped, so create_all() runs exactly once.
# Without these imports, models that are only imported via app.main (lazy)
# may be missing from the in-memory schema when tests run in alphabetical order.
import app.models  # noqa: F401


@pytest.fixture(scope="session")
def test_settings():
    """Test settings with in-memory SQLite."""
    return Settings(
        database_url="sqlite:///:memory:",
        debug=True,
        log_level="DEBUG",
    )


@pytest.fixture(scope="session")
def engine(test_settings):
    """Create test database engine."""
    engine = create_engine(
        test_settings.database_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(engine):
    """Create a new database session for each test.

    Cleans all tables after each test so that services which call
    ``commit()`` internally (e.g. MappingService) do not leak state
    between tests.
    """
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
