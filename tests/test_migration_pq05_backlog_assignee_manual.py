"""pq05: признак ручного исполнителя строки — вверх, вниз, снова вверх; Postgres."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = {"assignee_manual", "assignee_jira_account_at_choice"}


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
        return {c["name"] for c in sa.inspect(engine).get_columns("backlog_items")}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "pq05.db"
    url = f"sqlite:///{db_path.as_posix()}"
    _alembic(url, "upgrade", "head")
    assert COLUMNS <= _columns(db_path)
    _alembic(url, "downgrade", "pq03_issue_plan_sources")
    assert not (COLUMNS & _columns(db_path))
    _alembic(url, "upgrade", "head")
    assert COLUMNS <= _columns(db_path)


def test_postgres_boolean_default_is_false():
    """На Postgres значение по умолчанию — false, а не 0 (прод падал на v1.9.0).
    SQL берём в офлайн-режиме — сервер Postgres не нужен."""
    sql = _alembic(
        "postgresql://offline:offline@localhost:1/offline",
        "upgrade", "pq03_issue_plan_sources:pq05_backlog_assignee_manual", "--sql",
    )
    assert "ADD COLUMN assignee_manual BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ADD COLUMN assignee_jira_account_at_choice VARCHAR(128)" in sql
