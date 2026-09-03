"""Полная цепочка миграций на чистой базе.

Прод упал при установке v1.6.0: `k07a_kpi_seed_defaults` вызывал сегодняшний
`seed_defaults()`, а тот пишет в `kpi_profile_roles` — таблицу, которую создаёт
только `k13a`. На dev-базах таблица уже была (create_all), поэтому цепочку
никто не проверял: тесты гоняются на `create_all`, а не на `alembic upgrade`.

Этот тест поднимает пустую базу и прогоняет `alembic upgrade head` целиком —
любая миграция, опирающаяся на состояние, которого на её ревизии ещё нет,
падает здесь, а не на сервере.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent


def _upgrade_head(db_path: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )


def test_upgrade_head_on_empty_database(tmp_path):
    db_path = tmp_path / "fresh.db"
    result = _upgrade_head(db_path)
    assert result.returncode == 0, (
        f"alembic upgrade head упал на чистой базе:\n{result.stdout}\n{result.stderr}"
    )

    # Профиль «Аналитик» после установки с нуля обязан оценивать те же роли,
    # что и на обновлённой базе, — иначе ведомость KPI пустая.
    con = sqlite3.connect(db_path)
    try:
        roles = {row[0] for row in con.execute("SELECT role_code FROM kpi_profile_roles")}
    finally:
        con.close()
    assert roles == {"analyst", "RP"}


def test_upgrade_head_on_empty_postgres():
    """Та же цепочка на Postgres.

    Прод упал при обновлении до v1.9.0: булеву колонку создавали со значением
    по умолчанию `0` — SQLite молча глотает, Postgres отвергает по типу.
    Тест на SQLite такое не ловит в принципе, поэтому цепочка гоняется и на
    Postgres, когда он доступен (CI, локальный контейнер).
    """
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url.startswith("postgresql"):
        pytest.skip("нужен Postgres: TEST_DATABASE_URL")

    base, _, _ = url.rpartition("/")
    fresh_db = "fresh_migrations_test"
    admin = sa.create_engine(f"{base}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as con:
            con.execute(sa.text(f'DROP DATABASE IF EXISTS "{fresh_db}"'))
            con.execute(sa.text(f'CREATE DATABASE "{fresh_db}"'))

        env = {**os.environ, "DATABASE_URL": f"{base}/{fresh_db}"}
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False,
        )
        assert result.returncode == 0, (
            "alembic upgrade head упал на чистой базе Postgres:\n"
            f"{result.stdout}\n{result.stderr}"
        )
    finally:
        with admin.connect() as con:
            con.execute(sa.text(f'DROP DATABASE IF EXISTS "{fresh_db}"'))
        admin.dispose()
