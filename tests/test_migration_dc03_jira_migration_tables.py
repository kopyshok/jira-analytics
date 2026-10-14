"""dc03: таблицы отчёта и решений переезда; повторный запуск на базе из create_all не падает."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

from app.models.jira_migration import JiraMigrationDecision, JiraMigrationReport

REPO_ROOT = Path(__file__).resolve().parent.parent
TABLES = {"jira_migration_reports", "jira_migration_decisions"}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _tables(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_and_downgrade_drops(tmp_path):
    db = tmp_path / "m.db"
    _alembic(db, "upgrade", "dc03_jira_migration_tables")
    assert TABLES <= _tables(db)

    _alembic(db, "downgrade", "dc02_employee_jira_username")
    assert not (TABLES & _tables(db))


def test_upgrade_skips_tables_from_create_all(tmp_path):
    db = tmp_path / "pre.db"
    _alembic(db, "upgrade", "dc02_employee_jira_username")
    engine = sa.create_engine(f"sqlite:///{db.as_posix()}")
    try:
        JiraMigrationReport.__table__.create(engine)
        JiraMigrationDecision.__table__.create(engine)
    finally:
        engine.dispose()

    _alembic(db, "upgrade", "dc03_jira_migration_tables")
    assert TABLES <= _tables(db)
