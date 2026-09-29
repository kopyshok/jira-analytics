"""Сборка обезличенной демо-базы для съёмки роликов (локальный инструмент, в приложение не входит).

    py -3.10 scripts/demo_db/build_demo_db.py --source data/jira_analytics.db --out data/demo.db

1. Консистентная копия исходника (sqlite backup API; исходник открыт только на чтение).
2. Обезличивание (anonymize.py) по отражённой схеме.
3. Демо-пользователь demo@example.com / demo12345 (руководитель демо-команды; «Что нового»
   и автооткрытие «Первых шагов» отмечены просмотренными).
4. Проверка утечек (leak_check.py): находки → печать, выходной файл удаляется, код 1.
5. VACUUM и сводка.

После сборки схема ветки: alembic stamp + upgrade (см. план).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password  # noqa: E402
from scripts.demo_db import leak_check  # noqa: E402
from scripts.demo_db.anonymize import anonymize  # noqa: E402

DEFAULT_PRIMARY_TEAM = "Команда 1С (ERP - Товарный учет)"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"
DEMO_NAME = "Демо Пользователь"
MAX_PRINTED_FINDINGS = 50


def _copy(source: Path, out: Path) -> None:
    src = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(out)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def _remove(db: Path) -> None:
    for path in (db, *(db.with_name(db.name + s) for s in ("-wal", "-shm", "-journal"))):
        path.unlink(missing_ok=True)


def _ver_key(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.lstrip("v").split(".") if p.isdigit())


def _add_demo_user(conn: sqlite3.Connection, team: str, password_hash: str) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    if "onboarding" not in cols:
        # Та же колонка, что добавляет миграция ob01_onboarding (она пропустит уже существующую).
        conn.execute("ALTER TABLE users ADD COLUMN onboarding TEXT NOT NULL DEFAULT '{}'")
        cols.add("onboarding")
    versions = [r[0] for r in conn.execute("SELECT DISTINCT version FROM release_notes WHERE version IS NOT NULL")]
    now = datetime.utcnow().isoformat(sep=" ")
    values = {
        "id": str(uuid.uuid4()), "email": DEMO_EMAIL, "password_hash": password_hash,
        "display_name": DEMO_NAME, "role": "manager", "default_team": team, "is_active": 1,
        "selected_teams": json.dumps([team]), "selected_subgroups": "[]", "selected_period": "{}",
        "analytics_columns": "[]", "analytics_layout": "{}", "appearance_settings": "{}",
        "team_desk_filter": "{}", "onboarding": json.dumps({"auto_opened": True}),
        "last_seen_release_version": max(versions, key=_ver_key) if versions else None,
        "created_at": now, "updated_at": now,
    }
    values = {k: v for k, v in values.items() if k in cols}
    conn.execute("DELETE FROM users WHERE email = ?", (DEMO_EMAIL,))
    conn.execute(
        f"INSERT INTO users ({', '.join(values)}) VALUES ({', '.join('?' for _ in values)})",
        tuple(values.values()),
    )
    conn.commit()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Обезличенная демо-база для съёмки роликов")
    parser.add_argument("--source", type=Path, required=True, help="исходная база (только чтение)")
    parser.add_argument("--out", type=Path, required=True, help="выходная демо-база")
    parser.add_argument("--primary-team", default=DEFAULT_PRIMARY_TEAM,
                        help="команда, которая станет «Командой Альфа»")
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"Нет исходной базы: {args.source}")
        return 1
    if args.source.resolve() == args.out.resolve():
        print("Выходной файл совпадает с исходным")
        return 1
    started = time.monotonic()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _remove(args.out)
    print(f"Копия {args.source} → {args.out}…", flush=True)
    _copy(args.source, args.out)

    conn = sqlite3.connect(args.out)
    try:
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = OFF")
        password_hash = hash_password(DEMO_PASSWORD)
        sensitive = anonymize(conn, primary_team=args.primary_team, password_hash=password_hash)
        _add_demo_user(conn, sensitive.primary_team, password_hash)
        print("Проверка утечек…", flush=True)
        findings = leak_check.check(conn, sensitive)
        if findings:
            print(f"\nНАЙДЕНЫ УТЕЧКИ: {len(findings)}" + (" (показаны первые)" if len(findings) > 50 else ""))
            for finding in findings[:MAX_PRINTED_FINDINGS]:
                print(f"  {finding}")
            conn.close()
            _remove(args.out)
            print(f"\n{args.out} удалена.")
            return 1
        print("Утечек нет. Сжатие…", flush=True)
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("VACUUM")
    finally:
        conn.close()

    s = sensitive.stats
    size_mb = args.out.stat().st_size / 1024 / 1024
    print(
        f"\nГотово за {time.monotonic() - started:.0f} с: {args.out} ({size_mb:.0f} МБ)\n"
        f"  людей: {s['people']} (учёток {s['accounts']}, e-mail {s['emails']}), команд: {s['teams']}, "
        f"групп: {s['subgroups']}, проектов: {s['projects']}, заказчиков: {s['customers']}, "
        f"задач: {s['issues']}\n"
        f"  вход: {DEMO_EMAIL} / {DEMO_PASSWORD}, команда «{sensitive.primary_team}»"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
