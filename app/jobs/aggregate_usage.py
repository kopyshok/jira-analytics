"""Cron-job: ежедневно агрегировать usage_events и удалять старые."""
import logging
from datetime import datetime, timedelta
from typing import Callable

from app.services.usage_service import UsageService

logger = logging.getLogger(__name__)


def aggregate_usage_job(
    *, _session_factory: Callable | None = None, retention_days: int = 90,
) -> None:
    """Свернуть вчерашний день в usage_daily, удалить события старше retention."""
    own_session = _session_factory is None
    if _session_factory is None:
        from app.database import SessionLocal
        factory: Callable = SessionLocal
    else:
        factory = _session_factory

    db = factory()
    try:
        svc = UsageService(db)
        yesterday = (datetime.utcnow() - timedelta(days=1)).date()
        upserted = svc.aggregate_day(yesterday)
        deleted = svc.cleanup_old_events(retention_days=retention_days)
        logger.info(
            "aggregate_usage_job: upserted=%d daily rows, deleted=%d old events",
            upserted, deleted,
        )
    finally:
        if own_session:
            db.close()
