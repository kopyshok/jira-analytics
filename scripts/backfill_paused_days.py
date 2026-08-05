"""Разовый пересчёт дней простоя («Приостановлено») по всем задачам scope.

Дальше значение поддерживает обычная синхронизация задач.

Usage:
    py -3.10 scripts/backfill_paused_days.py
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.connectors.jira_client import JiraClient
from app.database import SessionLocal
from app.models.project import Project
from app.services.sync_service import SyncService


async def main() -> None:
    db = SessionLocal()
    try:
        keys = [p.key for p in db.query(Project).all()]
        print(f"Проектов: {len(keys)}")
        async with JiraClient.from_db(db) as jira:
            updated = await SyncService(db, jira).sync_paused_days(keys)
        print(f"Обновлено задач: {updated}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
