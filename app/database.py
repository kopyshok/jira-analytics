"""Database configuration and session management."""

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def _engine_kwargs(database_url: str, echo: bool) -> dict[str, object]:
    kwargs: dict[str, object] = {"echo": echo}
    if _is_sqlite_url(database_url):
        kwargs["connect_args"] = {"check_same_thread": False}
    return kwargs


engine = create_engine(settings.database_url, **_engine_kwargs(settings.database_url, settings.debug))


if _is_sqlite_url(settings.database_url):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Применить SQLite PRAGMA для каждого нового connection.

        - foreign_keys=ON — обязательное FK enforcement
        - journal_mode=WAL — write-ahead log: быстрее записи + concurrent reads
        - synchronous=NORMAL — c WAL даёт data integrity без cost of FULL fsync
          (теряется только последний commit на power loss, не consistency)
        - cache_size=-64000 — 64MB page cache (по умолчанию 2MB)
        - temp_store=MEMORY — temp tables в памяти, не на диск
        - mmap_size=268435456 — 256MB memory-mapped IO для read-heavy запросов
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA cache_size=-64000")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute("PRAGMA mmap_size=268435456")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for database session (for use outside FastAPI)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
