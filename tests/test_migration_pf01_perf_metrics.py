"""pf01: таблицы замеров быстродействия.

Настоящая цепочка на пустой SQLite. Идемпотентность: локальная база может уже
иметь таблицы от create_all — миграция их пропускает, а не падает.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
TABLES = {"perf_minute", "perf_slow_request", "perf_server_snapshot"}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _tables(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def test_upgrade_creates_tables_and_downgrade_drops(tmp_path):
    db_path = tmp_path / "pf01.db"
    _alembic(db_path, "upgrade", "pf01_perf_metrics")
    assert TABLES <= _tables(db_path)

    con = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(perf_minute)")}
    finally:
        con.close()
    assert {"minute", "route", "method", "count", "total_ms", "max_ms", "h0", "h10",
            "errors_5xx", "db_count", "db_ms", "created_at", "updated_at"} <= cols

    _alembic(db_path, "downgrade", "iv01_clear_frozen_involvement")
    assert not (TABLES & _tables(db_path))


def test_upgrade_skips_tables_created_by_create_all(tmp_path):
    db_path = tmp_path / "pf01_existing.db"
    _alembic(db_path, "upgrade", "iv01_clear_frozen_involvement")

    from app.database import Base
    import app.models  # noqa: F401

    eng = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        Base.metadata.create_all(
            bind=eng, tables=[Base.metadata.tables[t] for t in sorted(TABLES)],
        )
    finally:
        eng.dispose()

    _alembic(db_path, "upgrade", "pf01_perf_metrics")
    assert TABLES <= _tables(db_path)
