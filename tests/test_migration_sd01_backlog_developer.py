"""sd01: разработчик строки бэклога и снимка — вверх, вниз, снова вверх."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _columns(db_path: Path, table: str) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "sd01.db"
    url = f"sqlite:///{db_path.as_posix()}"
    _alembic(url, "upgrade", "head")
    assert "developer_employee_id" in _columns(db_path, "backlog_items")
    assert "developer_employee_id" in _columns(db_path, "scenario_allocation_snapshots")
    _alembic(url, "downgrade", "nw01_normed_reserve")
    assert "developer_employee_id" not in _columns(db_path, "backlog_items")
    assert "developer_employee_id" not in _columns(db_path, "scenario_allocation_snapshots")
    _alembic(url, "upgrade", "head")
    assert "developer_employee_id" in _columns(db_path, "backlog_items")


def test_postgres_offline_sql():
    sql = _alembic(
        "postgresql://offline:offline@localhost:1/offline",
        "upgrade", "nw01_normed_reserve:sd01_backlog_developer", "--sql",
    )
    assert "ADD COLUMN developer_employee_id VARCHAR(36)" in sql
