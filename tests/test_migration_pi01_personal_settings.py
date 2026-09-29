"""pi01: личная вовлечённость и личные нормированные работы сотрудника."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
PREV = "sd01_backlog_developer"
REV = "pi01_personal_settings"


def _alembic(db_url: str, *args: str) -> str:
    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"
    return result.stdout


def _tables(url: str) -> set[str]:
    engine = sa.create_engine(url)
    with engine.connect() as c:
        names = set(sa.inspect(c).get_table_names())
    engine.dispose()
    return names


def test_upgrade_downgrade_upgrade(tmp_path):
    url = f"sqlite:///{(tmp_path / 'pi01.db').as_posix()}"
    _alembic(url, "upgrade", REV)

    engine = sa.create_engine(url)
    with engine.connect() as c:
        insp = sa.inspect(c)
        cols = {x["name"] for x in insp.get_columns("employee_personal_settings")}
        normed_cols = {x["name"] for x in insp.get_columns("employee_personal_normed")}
        uniques = {u["name"] for u in insp.get_unique_constraints("employee_personal_settings")}
    engine.dispose()
    assert {"id", "employee_id", "effective_year", "effective_quarter", "involvement",
            "normed_custom", "created_at", "updated_at"} <= cols
    assert {"id", "setting_id", "work_type_id", "percent_of_norm"} <= normed_cols
    assert "uq_employee_personal_setting_scope" in uniques

    _alembic(url, "downgrade", PREV)
    assert not {"employee_personal_settings", "employee_personal_normed"} & _tables(url)

    _alembic(url, "upgrade", REV)
    assert {"employee_personal_settings", "employee_personal_normed"} <= _tables(url)


def test_upgrade_skips_tables_created_by_create_all(tmp_path):
    """Dev-база получает таблицы от create_all в тестах раньше миграции."""
    from app.models import EmployeePersonalNormed, EmployeePersonalSetting

    url = f"sqlite:///{(tmp_path / 'pi01b.db').as_posix()}"
    _alembic(url, "upgrade", PREV)
    engine = sa.create_engine(url)
    EmployeePersonalSetting.__table__.create(engine)
    EmployeePersonalNormed.__table__.create(engine)
    engine.dispose()

    _alembic(url, "upgrade", REV)

    assert {"employee_personal_settings", "employee_personal_normed"} <= _tables(url)
