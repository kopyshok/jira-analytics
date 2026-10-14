"""dc01: состояние переезда — pending при задачах в базе, done на свежей установке.

Настоящая цепочка миграций на временной SQLite.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY = "jira_migration_state"


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _state(db_path: Path):
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT value FROM app_settings WHERE key = ?", (KEY,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def _insert_minimal(db_path: Path, table: str, values: dict) -> None:
    """Вставить строку, заполнив обязательные колонки без значения по умолчанию."""
    con = sqlite3.connect(db_path)
    try:
        row = dict(values)
        for _cid, name, col_type, notnull, default, pk in con.execute(f"PRAGMA table_info({table})"):
            if name in row or not (notnull or pk) or default is not None:
                continue
            kind = (col_type or "").upper()
            if any(t in kind for t in ("INT", "FLOAT", "REAL", "NUMERIC", "BOOL")):
                row[name] = 0
            elif "DATE" in kind or "TIME" in kind:
                row[name] = "2026-01-01 00:00:00"
            else:
                row[name] = f"{table}-{name}"
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        con.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(row.values()))
        con.commit()
    finally:
        con.close()


def test_fresh_install_is_done(tmp_path):
    db = tmp_path / "fresh.db"
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    assert _state(db) == "done"


def test_existing_issues_make_pending(tmp_path):
    db = tmp_path / "with_issues.db"
    _alembic(db, "upgrade", "pf01_perf_metrics")
    _insert_minimal(db, "issues", {"id": "i1"})
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    assert _state(db) == "pending"


def test_existing_value_kept_and_downgrade_removes(tmp_path):
    db = tmp_path / "kept.db"
    _alembic(db, "upgrade", "pf01_perf_metrics")
    _insert_minimal(db, "issues", {"id": "i1"})
    _insert_minimal(db, "app_settings", {"id": "s1", "key": KEY, "value": "done"})
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    assert _state(db) == "done"

    _alembic(db, "downgrade", "pf01_perf_metrics")
    assert _state(db) is None
