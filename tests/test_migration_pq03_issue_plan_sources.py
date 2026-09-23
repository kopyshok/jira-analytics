"""pq03: колонки кандидатов оценки и выбора при споре — вверх, вниз, снова вверх."""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

REPO_ROOT = Path(__file__).resolve().parent.parent
COLUMNS = {"planned_hours_sources", "planned_hours_choice"}


def _alembic(db_path: Path, *args: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)}:\n{result.stdout}\n{result.stderr}"


def _issue_columns(db_path: Path) -> set[str]:
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        return {c["name"] for c in sa.inspect(engine).get_columns("issues")}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade(tmp_path):
    db_path = tmp_path / "pq03.db"
    _alembic(db_path, "upgrade", "head")
    assert COLUMNS <= _issue_columns(db_path)
    _alembic(db_path, "downgrade", "pq01_service_epic_off_plan")
    assert not (COLUMNS & _issue_columns(db_path))
    _alembic(db_path, "upgrade", "head")
    assert COLUMNS <= _issue_columns(db_path)
