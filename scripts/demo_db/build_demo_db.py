"""Сборка обезличенной демо-базы для съёмки роликов (локальный инструмент, в приложение не входит).

    py -3.10 scripts/demo_db/build_demo_db.py --source data/jira_analytics.db --out data/demo.db [--force]

Сборка идёт во временный файл <out>.tmp; при любой ошибке, прерывании или найденной утечке
он удаляется, и на месте --out не остаётся частично обезличенной копии. Готовый файл
подменяет --out только после проверки утечек, сжатия и создания демо-пользователя.
Существующий --out перезаписывается только с --force; файл с именем jira_analytics.db
и сам исходник выходом быть не могут.

1. Консистентная копия исходника (sqlite backup API; исходник открыт только на чтение).
2. Обезличивание (anonymize.py) по отражённой схеме.
3. Демо-пользователь demo@example.com / demo12345 (руководитель демо-команды; «Что нового»
   и автооткрытие «Первых шагов» отмечены просмотренными).
4. Проверка утечек (leak_check.py): находки → печать, временный файл удаляется, код 1.
5. VACUUM, подмена --out и сводка.

После сборки схема ветки: alembic stamp + upgrade (см. план).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password  # noqa: E402
from scripts.demo_db import leak_check  # noqa: E402
from scripts.demo_db.anonymize import Sensitive, anonymize  # noqa: E402

DEFAULT_PRIMARY_TEAM = "Команда 1С (ERP - Товарный учет)"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"
DEMO_NAME = "Демо Пользователь"
MAX_PRINTED_FINDINGS = 50
PROTECTED_NAME = "jira_analytics.db"  # имя рабочей базы: её нельзя перезаписать даже с --force
SIDE_SUFFIXES = ("-wal", "-shm", "-journal")


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


def _remove_sides(db: Path) -> None:
    for suffix in SIDE_SUFFIXES:
        db.with_name(db.name + suffix).unlink(missing_ok=True)


def _remove(db: Path) -> None:
    db.unlink(missing_ok=True)
    _remove_sides(db)


def _same_file(a: Path, b: Path) -> bool:
    if a.resolve() == b.resolve():
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


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


def _build(source: Path, tmp: Path, primary_team: str) -> Optional[Sensitive]:
    """Собрать демо-базу в tmp. None — найдены утечки (напечатаны)."""
    print(f"Копия {source} → {tmp}…", flush=True)
    _copy(source, tmp)
    conn = sqlite3.connect(tmp)
    try:
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = OFF")
        password_hash = hash_password(DEMO_PASSWORD)
        sensitive = anonymize(conn, primary_team=primary_team, password_hash=password_hash)
        _add_demo_user(conn, sensitive.primary_team, password_hash)
        print("Проверка утечек…", flush=True)
        findings = leak_check.check(conn, sensitive)
        if findings:
            more = " (показаны первые)" if len(findings) > MAX_PRINTED_FINDINGS else ""
            print(f"\nНАЙДЕНЫ УТЕЧКИ: {len(findings)}{more}")
            for finding in findings[:MAX_PRINTED_FINDINGS]:
                print(f"  {finding}")
            return None
        print("Утечек нет. Сжатие…", flush=True)
        conn.execute("PRAGMA journal_mode = DELETE")
        conn.execute("VACUUM")
        return sensitive
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Обезличенная демо-база для съёмки роликов")
    parser.add_argument("--source", type=Path, required=True, help="исходная база (только чтение)")
    parser.add_argument("--out", type=Path, required=True, help="выходная демо-база")
    parser.add_argument("--primary-team", default=DEFAULT_PRIMARY_TEAM,
                        help="команда, которая станет «Командой Альфа»")
    parser.add_argument("--force", action="store_true", help="перезаписать существующий --out")
    args = parser.parse_args(argv)
    source: Path = args.source
    out: Path = args.out

    if not source.is_file():
        print(f"Нет исходной базы: {source}")
        return 1
    if _same_file(source, out):
        print("Выходной файл совпадает с исходным")
        return 1
    if out.name.lower() == PROTECTED_NAME:
        print(f"Выходной файл не может называться {PROTECTED_NAME}: это имя рабочей базы")
        return 1
    if out.exists() and not args.force:
        print(f"{out} уже есть. Перезаписать: --force")
        return 1

    started = time.monotonic()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    _remove(tmp)
    try:
        sensitive = _build(source, tmp, args.primary_team)
        if sensitive is not None:
            _remove_sides(tmp)
            _remove_sides(out)
            os.replace(tmp, out)
    except BaseException:
        _remove(tmp)
        print(f"\nСборка прервана, {tmp} удалена.")
        raise
    if sensitive is None:
        _remove(tmp)
        print(f"\n{tmp} удалена, {out} не изменена.")
        return 1

    s = sensitive.stats
    size_mb = out.stat().st_size / 1024 / 1024
    print(
        f"\nГотово за {time.monotonic() - started:.0f} с: {out} ({size_mb:.0f} МБ)\n"
        f"  людей: {s['people']} (учёток {s['accounts']}, e-mail {s['emails']}), команд: {s['teams']}, "
        f"групп: {s['subgroups']}, проектов: {s['projects']}, заказчиков: {s['customers']}, "
        f"задач: {s['issues']}\n"
        f"  вход: {DEMO_EMAIL} / {DEMO_PASSWORD}, команда «{sensitive.primary_team}»"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
