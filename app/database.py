"""Database configuration and session management."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import get_settings

settings = get_settings()


def _is_sqlite_url(database_url: str) -> bool:
    return make_url(database_url).get_backend_name() == "sqlite"


def postgres_connect_args(
    *,
    lock_timeout_s: int = settings.db_lock_timeout_seconds,
    idle_in_transaction_timeout_s: int = settings.db_idle_in_transaction_timeout_seconds,
) -> dict[str, object]:
    """Параметры подключения к Postgres: пределы ожидания и имя приложения.

    Без пределов ожидание чужой блокировки бесконечно — так 23.10.2026 встал
    прод. Имя приложения видно в списке подключений базы: админ сразу видит,
    чьё подключение держит блокировку.
    """
    return {
        "application_name": "jira-analytics",
        # Недоступная база не держит запрос минутами на установке соединения.
        "connect_timeout": 10,
        "options": (
            f"-c lock_timeout={lock_timeout_s * 1000}"
            f" -c idle_in_transaction_session_timeout={idle_in_transaction_timeout_s * 1000}"
        ),
    }


def _engine_kwargs(database_url: str, echo: bool) -> dict[str, object]:
    kwargs: dict[str, object] = {"echo": echo}
    if _is_sqlite_url(database_url):
        # timeout=30: запись ждёт, пока фоновый синк отпустит базу, а не падает
        # через 5 с дефолта с «database is locked».
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs["connect_args"] = postgres_connect_args()
        # Пул под FastAPI: sync-эндпоинты крутятся в threadpool (по умолчанию 40
        # потоков) плюс фоновые job'ы планировщика. Дефолтные 5+10 упираются в
        # лимит и отдают 500 «QueuePool limit reached» под всплеском запросов.
        # Сверху 40 потоков — рабочие потоки asyncio.to_thread и синк в цикле:
        # синк, ждущий свободное соединение, держал бы весь цикл (до 30 с).
        # pre_ping отсеивает соединения, закрытые сервером БД за время простоя.
        kwargs["pool_size"] = 20
        kwargs["max_overflow"] = 40
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800
    return kwargs


def _ensure_sqlite_dir(database_url: str) -> None:
    """Создать каталог под файл БД: на чистой машине его ещё нет.

    Без этого SQLite падает с «unable to open database file» — так CI ронял
    все тесты, которые ходят через реальный engine приложения.
    """
    if not _is_sqlite_url(database_url):
        return
    db_path = make_url(database_url).database
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

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
