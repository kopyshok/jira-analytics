"""wl01: таблица списка наблюдения ресурсного плана.

Настоящая цепочка на пустой SQLite: создаёт таблицу; повторный запуск на базе,
где таблица уже есть (локальная база после create_all в тестах), не падает."""
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


def _columns(db_path: Path) -> set:
    con = sqlite3.connect(db_path)
    try:
        return {r[1] for r in con.execute("PRAGMA table_info(resource_plan_watch)")}
    finally:
        con.close()


def test_upgrade_creates_table_and_skips_existing(tmp_path):
    db_path = tmp_path / "wl01.db"
    _alembic(db_path, "upgrade", "wl01_plan_watchlist")
    assert _columns(db_path) == {"id", "plan_id", "employee_id", "created_at", "updated_at"}

    # Таблица уже есть, а ревизия — предыдущая: миграция её пропускает.
    _alembic(db_path, "stamp", "iv01_clear_frozen_involvement")
    _alembic(db_path, "upgrade", "wl01_plan_watchlist")
    assert _columns(db_path) == {"id", "plan_id", "employee_id", "created_at", "updated_at"}

    _alembic(db_path, "downgrade", "iv01_clear_frozen_involvement")
    assert _columns(db_path) == set()
