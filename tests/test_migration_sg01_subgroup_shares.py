"""sg01: таблица долей групп и перенос нынешней группы участия."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
PREV = "pi01_personal_settings"
REV = "sg01_subgroup_shares"


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def test_copies_current_group_as_base_record(tmp_path):
    url = f"sqlite:///{(tmp_path / 'sg01.db').as_posix()}"
    _alembic(url, "upgrade", PREV)
    engine = sa.create_engine(url)
    now = "2026-09-29 00:00:00"
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO employees (id, jira_account_id, display_name, is_active, created_at, updated_at) "
            "VALUES ('e1', 'a1', 'Иванов', 1, :n, :n), ('e2', 'a2', 'Петров', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO teams (id, name, has_subgroups, created_at, updated_at) "
            "VALUES ('t1', 'T', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO team_subgroups (id, team_id, name, sort_order, created_at, updated_at) "
            "VALUES ('g1', 't1', 'A', 1, :n, :n), ('g2', 't1', 'B', 2, :n, :n)"
        ), {"n": now})
        # e1 состоит в T двумя периодами с разными группами — берём группу
        # самого позднего периода (g2, joined_at 2026-06-01).
        # e2 состоит в другой команде U, но с группой g1 — та принадлежит T,
        # а не U, поэтому её переносить нельзя.
        c.execute(sa.text(
            "INSERT INTO employee_teams (id, employee_id, team, is_primary, subgroup_id, joined_at, created_at) "
            "VALUES "
            "('m1', 'e1', 'T', 1, 'g1', '2026-01-01', :n), "
            "('m1b', 'e1', 'T', 0, 'g2', '2026-06-01', :n), "
            "('m2', 'e2', 'T', 1, NULL, NULL, :n), "
            "('m3', 'e2', 'U', 0, 'g1', '2026-01-01', :n)"
        ), {"n": now})
    engine.dispose()

    _alembic(url, "upgrade", REV)

    def _rows():
        engine = sa.create_engine(url)
        with engine.connect() as c:
            rows = c.execute(sa.text(
                "SELECT employee_id, team, valid_from, subgroup_id, percent FROM employee_subgroup_shares"
            )).all()
        engine.dispose()
        return [tuple(r) for r in rows]

    assert _rows() == [("e1", "T", None, "g2", 100)]

    _alembic(url, "downgrade", PREV)
    _alembic(url, "upgrade", REV)
    assert _rows() == [("e1", "T", None, "g2", 100)]


def test_upgrade_skips_table_created_by_create_all(tmp_path):
    from app.models import EmployeeSubgroupShare

    url = f"sqlite:///{(tmp_path / 'sg01b.db').as_posix()}"
    _alembic(url, "upgrade", PREV)
    engine = sa.create_engine(url)
    EmployeeSubgroupShare.__table__.create(engine)
    engine.dispose()

    _alembic(url, "upgrade", REV)


def test_upgrade_copies_rows_when_table_precreated_with_data(tmp_path):
    """Таблица уже создана (create_all) и есть с чем переносить — строки переносятся."""
    from app.models import EmployeeSubgroupShare

    url = f"sqlite:///{(tmp_path / 'sg01c.db').as_posix()}"
    _alembic(url, "upgrade", PREV)
    engine = sa.create_engine(url)
    EmployeeSubgroupShare.__table__.create(engine)
    now = "2026-09-29 00:00:00"
    with engine.begin() as c:
        c.execute(sa.text(
            "INSERT INTO employees (id, jira_account_id, display_name, is_active, created_at, updated_at) "
            "VALUES ('e1', 'a1', 'Иванов', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO teams (id, name, has_subgroups, created_at, updated_at) "
            "VALUES ('t1', 'T', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO team_subgroups (id, team_id, name, sort_order, created_at, updated_at) "
            "VALUES ('g1', 't1', 'A', 1, :n, :n)"
        ), {"n": now})
        c.execute(sa.text(
            "INSERT INTO employee_teams (id, employee_id, team, is_primary, subgroup_id, joined_at, created_at) "
            "VALUES ('m1', 'e1', 'T', 1, 'g1', '2026-01-01', :n)"
        ), {"n": now})
    engine.dispose()

    _alembic(url, "upgrade", REV)

    engine = sa.create_engine(url)
    with engine.connect() as c:
        rows = c.execute(sa.text(
            "SELECT employee_id, team, valid_from, subgroup_id, percent FROM employee_subgroup_shares"
        )).all()
    engine.dispose()
    assert [tuple(r) for r in rows] == [("e1", "T", None, "g1", 100)]
