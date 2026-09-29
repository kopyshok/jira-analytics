"""sg02: колонка группы у участия удалена, данные — в распределении."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
PREV = "sg01_subgroup_shares"
REV = "sg02_drop_employee_team_subgroup"
NOW = "2026-09-29 00:00:00"


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _columns(url):
    engine = sa.create_engine(url)
    with engine.connect() as c:
        cols = {x["name"] for x in sa.inspect(c).get_columns("employee_teams")}
    engine.dispose()
    return cols


def _fks_and_indexes(url):
    engine = sa.create_engine(url)
    with engine.connect() as c:
        insp = sa.inspect(c)
        fks = [fk["constrained_columns"] for fk in insp.get_foreign_keys("employee_teams")]
        ixs = [ix["column_names"] for ix in insp.get_indexes("employee_teams")]
    engine.dispose()
    return fks, ixs


def test_drop_and_restore(tmp_path):
    url = f"sqlite:///{(tmp_path / 'sg02.db').as_posix()}"
    _alembic(url, "upgrade", REV)
    assert "subgroup_id" not in _columns(url)
    fks, ixs = _fks_and_indexes(url)
    assert ["subgroup_id"] not in fks
    assert ["subgroup_id"] not in ixs

    _alembic(url, "downgrade", PREV)
    assert "subgroup_id" in _columns(url)
    fks, ixs = _fks_and_indexes(url)
    assert ["subgroup_id"] in fks
    assert ["subgroup_id"] in ixs

    _alembic(url, "upgrade", REV)
    assert "subgroup_id" not in _columns(url)


def test_downgrade_restores_group_active_today(tmp_path):
    """Откат возвращает в колонку группу, действующую сегодня.

    Целиком в одной группе — она; поделён — группа с наибольшей долей;
    сегодня записи ещё нет (все с будущей даты) — наибольшая доля первой записи.
    """
    url = f"sqlite:///{(tmp_path / 'sg02c.db').as_posix()}"
    _alembic(url, "upgrade", REV)
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO employees (id, jira_account_id, display_name, is_active, created_at, updated_at) "
            "VALUES ('e1', 'a1', 'Иванов', 1, :n, :n), ('e2', 'a2', 'Петров', 1, :n, :n), "
            "('e3', 'a3', 'Сидоров', 1, :n, :n), ('e4', 'a4', 'Козлов', 1, :n, :n), "
            "('e5', 'a5', 'Без записей', 1, :n, :n)"
        ), {"n": NOW})
        c.execute(sa.text(
            "INSERT INTO teams (id, name, has_subgroups, created_at, updated_at) "
            "VALUES ('t1', 'T', 1, :n, :n)"
        ), {"n": NOW})
        c.execute(sa.text(
            "INSERT INTO team_subgroups (id, team_id, name, sort_order, created_at, updated_at) "
            "VALUES ('g1', 't1', 'A', 1, :n, :n), ('g2', 't1', 'B', 2, :n, :n)"
        ), {"n": NOW})
        c.execute(sa.text(
            "INSERT INTO employee_teams (id, employee_id, team, is_primary, created_at) "
            "VALUES ('m1', 'e1', 'T', 1, :n), ('m2', 'e2', 'T', 1, :n), "
            "('m3', 'e3', 'T', 1, :n), ('m3b', 'e3', 'T', 1, :n), "
            "('m4', 'e4', 'T', 1, :n), ('m5', 'e5', 'T', 1, :n)"
        ), {"n": NOW})
        c.execute(sa.text(
            "INSERT INTO employee_subgroup_shares "
            "(id, employee_id, team, valid_from, subgroup_id, percent, created_at, updated_at) "
            "VALUES "
            # e1 — «A 100 %» с начала участия.
            "('s1', 'e1', 'T', NULL, 'g1', 100, :n, :n), "
            # e2 поделён 40/60 с начала участия — берём группу с 60 %.
            "('s2', 'e2', 'T', NULL, 'g1', 40, :n, :n), "
            "('s3', 'e2', 'T', NULL, 'g2', 60, :n, :n), "
            # e3 переведён в B в прошлом — сегодня он в B (обе строки участия).
            "('s4', 'e3', 'T', NULL, 'g1', 100, :n, :n), "
            "('s5', 'e3', 'T', '2020-01-01', 'g2', 100, :n, :n), "
            # e4 — только записи с будущих дат: берём наибольшую долю первой.
            "('s6', 'e4', 'T', '2099-01-01', 'g1', 30, :n, :n), "
            "('s7', 'e4', 'T', '2099-01-01', 'g2', 70, :n, :n), "
            "('s8', 'e4', 'T', '2100-01-01', 'g1', 100, :n, :n)"
        ), {"n": NOW})
    engine.dispose()

    _alembic(url, "downgrade", PREV)

    engine = sa.create_engine(url)
    with engine.connect() as c:
        rows = c.execute(sa.text("SELECT id, subgroup_id FROM employee_teams")).all()
    engine.dispose()
    assert dict(rows) == {
        "m1": "g1", "m2": "g2", "m3": "g2", "m3b": "g2", "m4": "g2", "m5": None,
    }


def test_upgrade_tolerates_missing_column(tmp_path):
    """Dev-база от create_all может не иметь колонки."""
    url = f"sqlite:///{(tmp_path / 'sg02b.db').as_posix()}"
    _alembic(url, "upgrade", REV)
    _alembic(url, "stamp", PREV)
    _alembic(url, "upgrade", REV)


def test_upgrade_drops_unnamed_foreign_key(tmp_path):
    """Таблица от create_all: внешний ключ без имени уходит вместе с колонкой."""
    url = f"sqlite:///{(tmp_path / 'sg02d.db').as_posix()}"
    engine = sa.create_engine(url)
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE employees (id VARCHAR(36) PRIMARY KEY)"))
        c.execute(sa.text("CREATE TABLE team_subgroups (id VARCHAR(36) PRIMARY KEY)"))
        c.execute(sa.text(
            "CREATE TABLE employee_teams ("
            "id VARCHAR(36) PRIMARY KEY, "
            "employee_id VARCHAR(36) NOT NULL REFERENCES employees (id) ON DELETE CASCADE, "
            "team VARCHAR(100) NOT NULL, "
            "subgroup_id VARCHAR(36) REFERENCES team_subgroups (id) ON DELETE SET NULL)"
        ))
        c.execute(sa.text(
            "CREATE INDEX ix_employee_teams_subgroup_id ON employee_teams (subgroup_id)"
        ))
        c.execute(sa.text("INSERT INTO employees VALUES ('e1')"))
        c.execute(sa.text("INSERT INTO employee_teams VALUES ('m1', 'e1', 'T', NULL)"))
    engine.dispose()
    fks, _ = _fks_and_indexes(url)
    assert ["subgroup_id"] in fks

    _alembic(url, "stamp", PREV)
    _alembic(url, "upgrade", REV)

    assert _columns(url) == {"id", "employee_id", "team"}
    fks, ixs = _fks_and_indexes(url)
    assert fks == [["employee_id"]]
    assert ixs == []
