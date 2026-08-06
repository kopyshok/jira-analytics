"""Разовая доработка данных: «автор задачи» = Автор из Jira, а не создатель.

До версии 1.6 синхронизация писала в «автора» создателя задачи. Создателя
сменить нельзя, и у задач, заведённых автоматикой, там навсегда числится
робот — из-за этого баги, связанные с такими задачами, не доставались никому
в KPI. Синхронизация исправлена, но уже прочитанные задачи нужно перечитать
один раз.

Выполняется автоматически при первом запуске новой версии, в фоне. Признак
выполнения хранится в настройках приложения, поэтому повторные запуски и
несколько рабочих процессов сразу — безопасны. После того как обновление
раскатано на всех окружениях, модуль можно удалить вместе с вызовом из
``app.main``.
"""
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.jira_client import JiraClient
from app.database import SessionLocal
from app.models.app_setting import AppSetting
from app.models.issue import Issue
from app.models.project import Project

logger = logging.getLogger(__name__)

FLAG_KEY = "backfill_issue_author_done"
FIELDS = ["summary", "issuetype", "status", "project", "reporter", "creator"]


RUNNING_PREFIX = "running:"
# Пересчёт идёт минут десять; если отметка «в работе» старше этого срока,
# значит сервис перезапустили посреди работы — задание можно забрать себе,
# иначе дозаполнение молча не доедет до конца ни на одном запуске.
STALE_AFTER_MINUTES = 60


def _claim(db: Session) -> bool:
    """Занять задание за собой. False — уже сделано или делает кто-то другой.

    Строка настройки уникальна по ключу, поэтому второй процесс, стартовавший
    одновременно, получит ошибку уникальности и просто не станет работать.
    """
    now = datetime.utcnow()
    existing = db.query(AppSetting).filter_by(key=FLAG_KEY).first()
    if existing is not None:
        value = existing.value or ""
        if not value.startswith(RUNNING_PREFIX):
            return False
        try:
            started = datetime.fromisoformat(value[len(RUNNING_PREFIX):])
        except ValueError:
            started = datetime.min
        if now - started < timedelta(minutes=STALE_AFTER_MINUTES):
            return False
        existing.value = RUNNING_PREFIX + now.isoformat(timespec="seconds")
        db.commit()
        return True

    db.add(AppSetting(key=FLAG_KEY,
                      value=RUNNING_PREFIX + now.isoformat(timespec="seconds")))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


def _release(db: Session) -> None:
    """Снять отметку, чтобы следующий запуск сервиса попробовал снова."""
    db.rollback()
    db.query(AppSetting).filter_by(key=FLAG_KEY).delete()
    db.commit()


async def backfill_issue_author_once(
    client: Optional[object] = None,
    _session_factory: Optional[Callable] = None,
) -> int:
    """Перечитать Автора всех задач из Jira. Возвращает число обновлённых задач.

    ``client`` — подменяемый клиент Jira для теста; в бою берётся клиент с
    учётными данными из настроек.
    """
    db = (_session_factory or SessionLocal)()
    try:
        if not _claim(db):
            return 0

        keys = [k for (k,) in db.query(Project.key).all()]
        if not keys:
            logger.info("backfill_issue_author: проектов нет, пропуск")
            return 0
        jql = "project in ({}) ORDER BY created ASC".format(
            ", ".join(f'"{k}"' for k in keys)
        )
        by_key = {i.key: i for i in db.query(Issue).all()}
        logger.info("backfill_issue_author: старт, задач в базе %d", len(by_key))

        changed = 0
        jira = client or JiraClient.from_db(db)
        async with jira as api:
            async for issue in api.iter_issues(jql=jql, max_results=100, fields=FIELDS):
                row = by_key.get(issue.key)
                if row is None:
                    continue
                author = issue.fields.reporter or issue.fields.creator
                account = author.jira_account_id if author else None
                if row.reporter_account_id == account:
                    continue
                row.reporter_account_id = account
                row.reporter_display_name = author.display_name if author else None
                changed += 1
                if changed % 500 == 0:
                    db.commit()

        flag = db.query(AppSetting).filter_by(key=FLAG_KEY).first()
        if flag is not None:
            flag.value = datetime.utcnow().isoformat(timespec="seconds")
        db.commit()
        logger.info("backfill_issue_author: готово, обновлено задач %d", changed)
        return changed
    except Exception as e:
        logger.warning("backfill_issue_author: не удалось (повтор при следующем "
                       "запуске): %s", e)
        try:
            _release(db)
        except Exception:
            logger.exception("backfill_issue_author: не удалось снять отметку")
        return 0
    finally:
        db.close()
