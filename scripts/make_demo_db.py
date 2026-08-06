"""Обезличенная копия рабочей базы для показа сторонней компании.

Запуск:  py -3.10 scripts/make_demo_db.py

Делает файл `data/demo_anonymized.db`, живую базу не трогает. Сотрудники,
проекты и тексты задач заменяются на синтетические; секреты, история
синхронизаций, обратная связь и AI-кэши удаляются целиком.

Названия команд остаются настоящими — по ним ищут во время показа.

ponytail: один проход UPDATE/DELETE по копии вместо генератора фейковых данных —
структура и цифры остаются настоящими, читаемый текст пропадает.
"""

from __future__ import annotations

import secrets
import sqlite3
import string
import sys
from pathlib import Path

SRC = Path("data/jira_analytics.db")
DST = Path("data/demo_anonymized.db")

# Настройки, значения которых не должны уезжать с копией.
SECRET_KEY_MARKERS = (
    "token", "api_key", "apikey", "password", "secret", "credential",
    "url", "cloud_id", "email", "login", "user", "domain", "host",
)

# Таблицы, которые в демо-копии не нужны совсем.
DROP_ROWS = [
    "sync_run", "sync_state", "sync_schedule",          # история синхронизаций
    "usage_events", "usage_daily",                       # аналитика использования
    "feedback_items",                                    # обратная связь с текстами
    "project_ai_summaries", "issue_classifications",     # AI-тексты про реальные проекты
    "work_type_report_snapshots", "executive_dashboard_snapshots",
    "confluence_page_cache",
    "plan_audit", "plan_conflicts",                      # пересчитываются сами
    "comments",                                          # тела комментариев Jira
]


def label(n: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA ..."""
    out = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        out = string.ascii_uppercase[rem] + out
    return out


def copy_db() -> None:
    if not SRC.exists():
        sys.exit(f"Не найден файл базы: {SRC}")
    if DST.exists():
        DST.unlink()
    src = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
    dst = sqlite3.connect(DST)
    src.backup(dst)          # корректно забирает и незаписанный хвост WAL
    src.close()
    dst.close()


def anonymize(db: sqlite3.Connection, demo_password: str) -> None:
    cur = db.cursor()
    cur.execute("PRAGMA foreign_keys = OFF")

    # --- люди -------------------------------------------------------------
    employees = cur.execute(
        "SELECT id, jira_account_id FROM employees ORDER BY id"
    ).fetchall()
    cur.execute("CREATE TEMP TABLE acct_map(old TEXT PRIMARY KEY, new_id TEXT, new_name TEXT)")
    for i, (emp_id, acct) in enumerate(employees, start=1):
        name = f"Сотрудник {i}"
        new_acct = f"acct-{i:04d}"
        cur.execute(
            "UPDATE employees SET display_name=?, email=?, jira_account_id=?, "
            "avatar_url=NULL, department=NULL WHERE id=?",
            (name, f"user{i}@example.com", new_acct, emp_id),
        )
        if acct:
            cur.execute("INSERT OR REPLACE INTO acct_map VALUES (?,?,?)", (acct, new_acct, name))

    # имена исполнителя/автора в задачах — по тому же соответствию
    for col_acct, col_name in (
        ("assignee_account_id", "assignee_display_name"),
        ("reporter_account_id", "reporter_display_name"),
    ):
        cur.execute(
            f"UPDATE issues SET {col_name}=(SELECT new_name FROM acct_map WHERE old={col_acct}), "
            f"{col_acct}=(SELECT new_id FROM acct_map WHERE old={col_acct}) "
            f"WHERE {col_acct} IN (SELECT old FROM acct_map)"
        )
        # исполнитель/автор, которого нет в справочнике сотрудников — стереть,
        # иначе в копии остаётся настоящее имя из Jira
        cur.execute(
            f"UPDATE issues SET {col_name}=NULL, {col_acct}=NULL "
            f"WHERE {col_acct} IS NULL OR {col_acct} NOT LIKE 'acct-%'"
        )

    # копии имён в снимках сценариев
    cur.execute(
        "UPDATE scenario_team_snapshots SET display_name="
        "COALESCE((SELECT display_name FROM employees WHERE id=employee_id),'Сотрудник')"
    )
    for table in ("scenario_capacity_snapshots", "scenario_norm_snapshots", "scenario_absence_snapshots"):
        cur.execute(
            f"UPDATE {table} SET employee_name="
            "COALESCE((SELECT display_name FROM employees WHERE id=employee_id),'Сотрудник')"
        )

    # --- пользователи сервиса --------------------------------------------
    from app.core.security import hash_password

    pw_hash = hash_password(demo_password)
    for i, (uid,) in enumerate(cur.execute("SELECT id FROM users ORDER BY id").fetchall(), start=1):
        cur.execute(
            "UPDATE users SET email=?, display_name=?, password_hash=? WHERE id=?",
            (f"demo{i}@example.com", f"Пользователь {i}", pw_hash, uid),
        )
    # сохранённые фильтры прошлых владельцев прячут данные в демо
    cur.execute("UPDATE users SET selected_teams='[]', default_team=NULL")
    cur.execute("UPDATE release_notes SET created_by=NULL")
    cur.execute("UPDATE themes SET created_by=NULL")

    # публичные ссылки на рабочие столы — новые
    for (wid,) in cur.execute("SELECT id FROM work_desks").fetchall():
        cur.execute("UPDATE work_desks SET token=? WHERE id=?", (secrets.token_urlsafe(16), wid))

    # Названия команд сознательно остаются настоящими — по решению владельца
    # сервиса: в демо по ним ищут, а синтетические буквы делают показ неудобным.

    # --- проекты и ключи задач -------------------------------------------
    projects = cur.execute("SELECT id, key FROM projects ORDER BY key").fetchall()
    cur.execute("CREATE TEMP TABLE proj_map(pid TEXT PRIMARY KEY, oldk TEXT, newk TEXT)")
    for i, (pid, oldk) in enumerate(projects):
        newk = f"PR{label(i)}"
        cur.execute("INSERT INTO proj_map VALUES (?,?,?)", (pid, oldk, newk))
        cur.execute(
            "UPDATE projects SET key=?, name=?, description=NULL WHERE id=?",
            (newk, f"Проект {label(i)}", pid),
        )
    cur.execute(
        "UPDATE issues SET key=(SELECT p.newk || substr(issues.key, length(p.oldk)+1) "
        "FROM proj_map p WHERE p.pid=issues.project_id) "
        "WHERE project_id IN (SELECT pid FROM proj_map)"
    )
    cur.execute("UPDATE issues SET key='XX-' || rowid WHERE key IS NULL OR project_id IS NULL")
    for table, col in (
        ("scope_projects", "jira_project_key"),
        ("hierarchy_rule", "project_key"),
        ("scope_roots", "project_key"),
    ):
        cur.execute(
            f"UPDATE {table} SET {col}=(SELECT newk FROM proj_map WHERE oldk={col}) "
            f"WHERE {col} IN (SELECT oldk FROM proj_map)"
        )
    cur.execute("DELETE FROM category_overrides")   # ссылаются на старые ключи задач
    cur.execute("DELETE FROM scope_roots WHERE jira_issue_key IS NOT NULL")

    # --- тексты задач -----------------------------------------------------
    cur.execute(
        "UPDATE issues SET summary='Задача ' || key, description=NULL, goals=NULL, "
        "goal_text=NULL, current_behavior=NULL, category_context=NULL, "
        "environment=NULL, impact=NULL, risk=NULL"
    )
    cur.execute("UPDATE worklogs SET comment_text=NULL")

    # --- бэклог, сценарии, планы -----------------------------------------
    for i, (bid,) in enumerate(cur.execute("SELECT id FROM backlog_items ORDER BY id").fetchall(), 1):
        cur.execute(
            "UPDATE backlog_items SET title=?, customer=NULL, impact=NULL, risk=NULL WHERE id=?",
            (f"Инициатива {i}", bid),
        )
    cur.execute(
        "UPDATE scenario_allocation_snapshots SET "
        "title=COALESCE((SELECT title FROM backlog_items WHERE id=backlog_item_id),'Инициатива'), "
        "customer=NULL, impact=NULL, risk=NULL"
    )
    cur.execute(
        "UPDATE scenario_revision_items SET backlog_item_name="
        "COALESCE((SELECT title FROM backlog_items WHERE id=backlog_item_id),'Инициатива')"
    )
    for i, (sid,) in enumerate(cur.execute("SELECT id FROM planning_scenarios ORDER BY id").fetchall(), 1):
        cur.execute("UPDATE planning_scenarios SET name=? WHERE id=?", (f"Сценарий {i}", sid))
    cur.execute("UPDATE resource_plans SET label=NULL")
    cur.execute("UPDATE scenario_revisions SET note=NULL")
    for i, (tid,) in enumerate(cur.execute("SELECT id FROM themes ORDER BY id").fetchall()):
        cur.execute(
            "UPDATE themes SET name=?, description=NULL, aliases_json=NULL WHERE id=?",
            (f"Тема {label(i)}", tid),
        )

    # --- секреты и мусор --------------------------------------------------
    for (key,) in cur.execute("SELECT key FROM app_settings").fetchall():
        if any(m in key.lower() for m in SECRET_KEY_MARKERS):
            cur.execute("UPDATE app_settings SET value=NULL WHERE key=?", (key,))
    for table in DROP_ROWS:
        cur.execute(f"DELETE FROM {table}")
    cur.execute("DROP TABLE IF EXISTS _alembic_tmp_employees")

    db.commit()


def main() -> None:
    password = "demo-" + secrets.token_urlsafe(6)
    print(f"Копирую {SRC} -> {DST} ...")
    copy_db()
    db = sqlite3.connect(DST)
    try:
        anonymize(db, password)
        print("Сжимаю файл ...")
        db.execute("VACUUM")
    finally:
        db.close()
    size = DST.stat().st_size / 1024 / 1024
    print(f"\nГотово: {DST} ({size:.0f} МБ)")
    print(f"Вход в демо: любой из адресов demo1@example.com ... , пароль: {password}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    main()
