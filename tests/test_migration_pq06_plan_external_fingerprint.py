"""pq06: отпечаток учтённых броней у плана — вверх, вниз, снова вверх; Postgres."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMN = "external_fingerprint"


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _columns(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("resource_plans")}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "pq06.db"
    url = f"sqlite:///{db_path.as_posix()}"
    _alembic(url, "upgrade", "head")
    assert COLUMN in _columns(db_path)
    _alembic(url, "downgrade", "pq05_backlog_assignee_manual")
    assert COLUMN not in _columns(db_path)
    _alembic(url, "upgrade", "head")
    assert COLUMN in _columns(db_path)


def test_postgres_sql():
    """SQL для Postgres берём в офлайн-режиме — сервер Postgres не нужен."""
    sql = _alembic(
        "postgresql://offline:offline@localhost:1/offline",
        "upgrade", "pq05_backlog_assignee_manual:pq06_plan_external_fingerprint", "--sql",
    )
    assert "ALTER TABLE resource_plans ADD COLUMN external_fingerprint TEXT" in sql
