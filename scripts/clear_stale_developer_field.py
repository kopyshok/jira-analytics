"""Разовая чистка мёртвого поля «Разработчик» у переехавших задач.

Jira хранит значение поля и после переноса задачи в проект, где такого поля на
экране нет. Дальше значение чистит стадия синхронизации; этот скрипт нужен, чтобы
разобрать накопленное до её появления.

Usage:
    py -3.10 scripts/clear_stale_developer_field.py            # только показать
    py -3.10 scripts/clear_stale_developer_field.py --apply    # и записать
"""
import asyncio
import sys

sys.path.insert(0, ".")

from app.connectors.jira_client import JiraClient
from app.database import SessionLocal
from app.models import Issue, Project
from app.services.stale_field_cleanup import clear_stale_developer_field


async def main() -> None:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        async with JiraClient.from_db(db) as jira:
            result = await clear_stale_developer_field(db, jira, dry_run=not apply)
        print(
            f"Проектов проверено: {result['projects_checked']}, "
            f"без поля: {result['projects_stale']}, "
            f"задач {'очищено' if apply else 'под чистку'}: {result['issues_cleared']}"
        )
        if not apply:
            print("Записи не было. Повторите с --apply.")
            left = (
                db.query(Project.key, Issue.key, Issue.issue_type)
                .join(Project, Project.id == Issue.project_id)
                .filter(Issue.developer_account_id.isnot(None))
                .count()
            )
            print(f"Задач с заполненным полем всего: {left}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
