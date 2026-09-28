"""nw01: вид работ у заблокированного периода и выбор вида у задач других команд."""
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


def test_month_close_blocks_get_support_work_type(tmp_path):
    url = f"sqlite:///{(tmp_path / 'nw01.db').as_posix()}"
    _alembic(url, "upgrade", "pq07_assignment_opo_part")
    engine = sa.create_engine(url)
    with engine.begin() as c:
        wt = c.execute(sa.text("SELECT id FROM mandatory_work_types WHERE code='support_consult'")).scalar()
        if wt is None:
            wt = "wt-support"
            c.execute(sa.text(
                "INSERT INTO mandatory_work_types (id, code, label, is_active, sort_order, "
                "subtracts_from_pool, is_system, theme_dict_version, created_at, updated_at) "
                "VALUES ('wt-support','support_consult','Сопровождение и консультация',1,3,1,1,1,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        for bid, reason in (("b1", " Закрытие месяца "), ("b2", "Обучение")):
            c.execute(sa.text(
                "INSERT INTO scheduled_blocks (id, team, start_date, end_date, reason, created_at, updated_at) "
                "VALUES (:id, 'ERP', '2026-10-05', '2026-10-07', :r, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
                {"id": bid, "r": reason})
    engine.dispose()

    _alembic(url, "upgrade", "head")

    engine = sa.create_engine(url)
    with engine.connect() as c:
        got = dict(c.execute(sa.text("SELECT id, work_type_id FROM scheduled_blocks")).all())
        cols = {x["name"] for x in sa.inspect(c).get_columns("team_work_type_overrides")}
    engine.dispose()
    assert got == {"b1": wt, "b2": None}
    assert {"team", "backlog_item_id", "work_type_id"} <= cols

    _alembic(url, "downgrade", "pq07_assignment_opo_part")
    _alembic(url, "upgrade", "head")
