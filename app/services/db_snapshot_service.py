"""Снимок рабочей БД в переносимый SQLite-файл.

Нужен, чтобы аналитик мог обновить локальную копию данными продуктива без
участия сисадмина: админ жмёт кнопку в интерфейсе, сервис собирает файл,
файл скачивается и подкладывается в локальный `data/`.

Работает через `Base.metadata`, поэтому источником может быть и Postgres,
и SQLite — vendor-specific SQL не используется.

ponytail: логика построчного копирования дублирует scripts/migrate_to_postgres.py
(обратное направление). Объединять, когда появится третий потребитель.
"""

from __future__ import annotations

import gzip
import logging
import os
import secrets
import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import Table, create_engine, inspect, select, text
from sqlalchemy.engine import Engine

import app.models  # noqa: F401 — регистрирует все таблицы в Base.metadata
from app.database import Base, engine as app_engine

logger = logging.getLogger(__name__)

EXPORT_DIR = Path("data") / "exports"
FILE_TTL = timedelta(hours=24)
BATCH_SIZE = 1000

# Кэши и runtime-состояние: восстанавливаются сами, переносить незачем.
SKIP_TABLES: set[str] = {
    "sync_state",
    "sync_run",
    "confluence_page_cache",
    "executive_dashboard_snapshots",
}

# Ключи настроек, значения которых не должны уезжать с сервера.
SECRET_KEY_MARKERS = ("token", "api_key", "password", "secret")


# --------------------------------------------------------------------------- #
# Копирование данных
# --------------------------------------------------------------------------- #

def _copy_table(
    source: Engine,
    target: Engine,
    table: Table,
    scrub: Callable[[dict], dict] | None = None,
) -> int:
    """Скопировать таблицу целиком батчами. Возвращает число перенесённых строк.

    Таблицы стримятся, а не читаются в память целиком: задач больше сотни тысяч,
    буферизация всей таблицы на сервере съела бы гигабайты.

    Порядок строк не выравнивается по родителям: в файле-приёмнике FK-проверки
    выключены (дефолт SQLite), а приложение включает их только на своих
    подключениях — на уже записанные строки это не влияет.
    """
    copied = 0
    batch: list[dict] = []

    def flush() -> None:
        nonlocal copied, batch
        if not batch:
            return
        with target.begin() as conn:
            conn.execute(table.insert(), batch)
        copied += len(batch)
        batch = []

    with source.connect() as conn:
        result = conn.execution_options(stream_results=True, yield_per=BATCH_SIZE).execute(
            select(table)
        )
        for row in result:
            values = dict(row._mapping)
            batch.append(scrub(values) if scrub is not None else values)
            if len(batch) >= BATCH_SIZE:
                flush()
        flush()
    return copied


# --------------------------------------------------------------------------- #
# Вычистка секретов
# --------------------------------------------------------------------------- #

def _make_scrubber(table_name: str, local_password_hash: str) -> Callable[[dict], dict] | None:
    """Заменить чувствительные значения перед записью в файл.

    Пароли пользователей заменяются одним общим локальным паролем, ключи
    доступа (Jira, LLM-провайдеры) обнуляются — их вводят локально заново.
    """
    if table_name == "users":
        def scrub_user(row: dict) -> dict:
            row["password_hash"] = local_password_hash
            return row
        return scrub_user

    if table_name == "app_settings":
        def scrub_setting(row: dict) -> dict:
            key = (row.get("key") or "").lower()
            if any(marker in key for marker in SECRET_KEY_MARKERS):
                row["value"] = None
            return row
        return scrub_setting

    return None


# --------------------------------------------------------------------------- #
# Состояние задачи (одна на процесс)
# --------------------------------------------------------------------------- #

@dataclass
class ExportJob:
    state: str = "idle"                   # idle | running | done | error
    started_at: datetime | None = None
    finished_at: datetime | None = None
    tables_total: int = 0
    tables_done: int = 0
    current_table: str | None = None
    rows_copied: int = 0
    error: str | None = None
    file_path: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    local_password: str | None = None
    revision: str | None = None
    per_table: dict[str, int] = field(default_factory=dict)


# ponytail: состояние в памяти — сервис запускается одним процессом uvicorn.
# Если появятся воркеры, переносить в БД или Redis.
_job = ExportJob()
_lock = threading.Lock()


def current_job() -> ExportJob:
    _cleanup_expired()
    return _job


def is_running() -> bool:
    return _job.state == "running"


def _cleanup_expired() -> None:
    """Удалить просроченный файл: копия всей базы не должна лежать вечно."""
    if _job.state != "done" or not _job.file_path or not _job.finished_at:
        return
    if datetime.now(timezone.utc) - _job.finished_at < FILE_TTL:
        return
    _discard_file(_job.file_path)
    _job.file_path = None
    _job.local_password = None
    _job.state = "idle"


def _discard_file(path: str | None) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _current_revision(source: Engine) -> str | None:
    with source.connect() as conn:
        if "alembic_version" not in inspect(source).get_table_names():
            return None
        return conn.scalar(text("SELECT version_num FROM alembic_version"))


def _tables_to_copy(source: Engine) -> list[Table]:
    existing = set(inspect(source).get_table_names())
    return [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in SKIP_TABLES and table.name in existing
    ]


def build_snapshot(source: Engine | None = None) -> ExportJob:
    """Собрать gzip-файл SQLite-снимка. Обновляет глобальное состояние задачи."""
    global _job
    source = source or app_engine
    with _lock:
        if _job.state == "running":
            raise RuntimeError("Выгрузка уже выполняется")
        _discard_file(_job.file_path)
        _job = ExportJob(
            state="running",
            started_at=datetime.now(timezone.utc),
            local_password=secrets.token_urlsafe(9),
        )
    job = _job

    tmp_dir = Path(tempfile.mkdtemp(prefix="db-snapshot-"))
    raw_path = tmp_dir / "snapshot.db"
    try:
        from app.core.security import hash_password

        password_hash = hash_password(job.local_password or "")
        revision = _current_revision(source)
        job.revision = revision

        target = create_engine(f"sqlite:///{raw_path}")
        Base.metadata.create_all(target)
        with target.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
            if revision:
                conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
                    {"rev": revision},
                )

        tables = _tables_to_copy(source)
        if not tables:
            raise RuntimeError("В источнике не найдено ни одной таблицы сервиса")
        job.tables_total = len(tables)
        for table in tables:
            job.current_table = table.name
            copied = _copy_table(
                source, target, table, _make_scrubber(table.name, password_hash)
            )
            job.per_table[table.name] = copied
            job.rows_copied += copied
            job.tables_done += 1
        job.current_table = None
        target.dispose()

        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        # Суффикс — чтобы две выгрузки в одну секунду не писали в один файл.
        file_name = f"jira_analytics_{stamp}_{secrets.token_hex(2)}.db.gz"
        out_path = EXPORT_DIR / file_name
        with open(raw_path, "rb") as src, gzip.open(out_path, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)

        job.file_path = str(out_path)
        job.file_name = file_name
        job.file_size = out_path.stat().st_size
        job.state = "done"
    except Exception as exc:  # noqa: BLE001 — состояние задачи должно отражать любую поломку
        logger.exception("Не удалось собрать снимок БД")
        job.state = "error"
        job.error = str(exc)
    finally:
        job.finished_at = datetime.now(timezone.utc)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return job
