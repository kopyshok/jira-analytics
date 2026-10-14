"""dc02: колонка employees.jira_username; повторный запуск на базе из create_all не падает."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _columns(db_path: Path) -> set[str]:
    con = sqlite3.connect(db_path)
    try:
        return {r[1] for r in con.execute("PRAGMA table_info(employees)")}
    finally:
        con.close()


def test_upgrade_adds_column_and_downgrade_drops(tmp_path):
    db = tmp_path / "dc02.db"
    _alembic(db, "upgrade", "dc02_employee_jira_username")
    assert "jira_username" in _columns(db)
    _alembic(db, "downgrade", "dc01_jira_sync_lock")
    assert "jira_username" not in _columns(db)


def test_upgrade_skips_existing_column(tmp_path):
    db = tmp_path / "dc02_existing.db"
    _alembic(db, "upgrade", "dc01_jira_sync_lock")
    con = sqlite3.connect(db)
    try:
        con.execute("ALTER TABLE employees ADD COLUMN jira_username VARCHAR(255)")
        con.commit()
    finally:
        con.close()
    _alembic(db, "upgrade", "dc02_employee_jira_username")
    assert "jira_username" in _columns(db)
