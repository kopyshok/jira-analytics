"""pq03: колонки кандидатов оценки и выбора при споре — вверх, вниз, снова вверх."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import Issue

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = {"planned_hours_sources", "planned_hours_choice"}


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.as_posix()}"


def _issue_columns(db_path: Path) -> set[str]:
    engine = sa.create_engine(_sqlite_url(db_path))
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("issues")}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    url = _sqlite_url(tmp_path / "pq03.db")
    _alembic(url, "upgrade", "head")
    assert COLUMNS <= _issue_columns(tmp_path / "pq03.db")
    _alembic(url, "downgrade", "pq01_service_epic_off_plan")
    assert not (COLUMNS & _issue_columns(tmp_path / "pq03.db"))
    _alembic(url, "upgrade", "head")
    assert COLUMNS <= _issue_columns(tmp_path / "pq03.db")


def test_postgres_migration_adds_jsonb():
    """На PostgreSQL колонки — JSONB: у простого json нет оператора равенства,
    и SELECT DISTINCT по строкам задач (Executive, отчёт по видам работ) падает.
    SQL миграции берём в офлайн-режиме — сервер Postgres не нужен."""
    sql = _alembic(
        "postgresql://offline:offline@localhost:1/offline",
        "upgrade", "pq01_service_epic_off_plan:pq03_issue_plan_sources", "--sql",
    )
    assert "ADD COLUMN planned_hours_sources JSONB" in sql
    assert "ADD COLUMN planned_hours_choice JSONB" in sql


def test_postgres_model_columns_are_jsonb():
    ddl = str(CreateTable(Issue.__table__).compile(dialect=postgresql.dialect()))
    assert "planned_hours_sources JSONB" in ddl
    assert "planned_hours_choice JSONB" in ddl
