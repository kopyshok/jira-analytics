"""iv01: вовлечённость больше не берётся из Jira и не копируется при
утверждении — миграция снимает все проценты у задач бэклога (фазы берут
личную настройку или справочник) и удаляет колонки вовлечённости у задач Jira.

Гоняется настоящая цепочка на пустой SQLite: пакетное удаление колонок
проверяется только так."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIELDS = ("involvement_analyst", "involvement_dev", "involvement_qa", "involvement_launch")


def _upgrade(db_path: Path, revision: str) -> None:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path.as_posix()}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_upgrade_clears_task_involvement_and_drops_jira_columns(tmp_path):
    db_path = tmp_path / "iv01.db"
    _upgrade(db_path, "ob01_onboarding")

    con = sqlite3.connect(db_path)
    try:
        now = "2026-09-30 00:00:00"
        con.execute(
            "INSERT INTO projects (id, jira_project_id, key, name, is_active, created_at, updated_at)"
            " VALUES ('p1', 'jp1', 'PRJ', 'P', 1, ?, ?)", (now, now),
        )
        con.execute(
            "INSERT INTO issues (id, jira_issue_id, key, summary, issue_type, status, project_id,"
            " involvement_analyst, created_at, updated_at)"
            " VALUES ('i1', 'j1', 'PRJ-1', 'S', 'Task', 'Open', 'p1', 0.6, ?, ?)", (now, now),
        )
        con.execute(
            "INSERT INTO backlog_items (id, title, issue_id, involvement_analyst, involvement_dev,"
            " involvement_qa, involvement_launch, duration_dev_days, created_at, updated_at)"
            " VALUES ('b1', 'T', 'i1', 0.7, 0.9, 0.5, 0.3, 4.0, ?, ?)", (now, now),
        )
        con.commit()
    finally:
        con.close()

    _upgrade(db_path, "iv01_clear_frozen_involvement")

    con = sqlite3.connect(db_path)
    try:
        row = con.execute(
            f"SELECT {', '.join(FIELDS)}, duration_dev_days FROM backlog_items WHERE id = 'b1'"
        ).fetchone()
        issue_cols = {r[1] for r in con.execute("PRAGMA table_info(issues)")}
        issue_key = con.execute("SELECT key FROM issues WHERE id = 'i1'").fetchone()
    finally:
        con.close()

    assert row == (None, None, None, None, 4.0)
    assert not issue_cols & set(FIELDS)
    assert issue_key == ("PRJ-1",)
