"""UsageService — запись raw событий + валидация."""
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import UsageEvent, UsageEventType


# Whitelist маршрутов SPA — нормализованные пути.
ALLOWED_PATHS: set[str] = {
    "/dashboard",
    "/analytics",
    "/projects",
    "/projects/:key",
    "/sync",
    "/categories",
    "/category-config",
    "/capacity",
    "/backlog",
    "/planning",
    "/scenarios/:id",
    "/scenarios/:id/edit",
    "/resource-planning",
    "/executive",
    "/themes",
    "/work-type-report",
    "/feedback",
    "/settings",
    "/login",
}

_MAX_TIME_SKEW = timedelta(hours=1)


class UsageService:
    def __init__(self, db: Session):
        self.db = db

    def record_events(self, *, user_id: str, events: Iterable[dict]) -> dict:
        """Batch insert. Тихо игнорирует мусор; возвращает счётчики."""
        now = datetime.utcnow()
        accepted = 0
        rejected = 0
        rows: list[UsageEvent] = []

        for ev in events:
            if not self._is_valid(ev, now):
                rejected += 1
                continue
            at_val = ev["at"]
            if isinstance(at_val, str):
                at_val = datetime.fromisoformat(at_val)
            if at_val.tzinfo is not None:
                at_val = at_val.astimezone(timezone.utc).replace(tzinfo=None)
            rows.append(UsageEvent(
                user_id=user_id,
                event_type=UsageEventType(ev["event_type"]),
                path=ev["path"],
                action_type=ev.get("action_type"),
                entity_id=ev.get("entity_id"),
                at=at_val,
            ))
            accepted += 1

        if rows:
            self.db.add_all(rows)
            self.db.commit()

        return {"accepted": accepted, "rejected": rejected}

    @staticmethod
    def _is_valid(ev: dict, now: datetime) -> bool:
        if ev.get("path") not in ALLOWED_PATHS:
            return False
        if ev.get("event_type") not in ("page_view", "heartbeat", "action"):
            return False
        if ev["event_type"] == "action" and not ev.get("action_type"):
            return False
        at = ev.get("at")
        if isinstance(at, str):
            try:
                at = datetime.fromisoformat(at)
            except ValueError:
                return False
        if not isinstance(at, datetime):
            return False
        if at.tzinfo is not None:
            at = at.astimezone(timezone.utc).replace(tzinfo=None)
        if abs((now - at).total_seconds()) > _MAX_TIME_SKEW.total_seconds():
            return False
        return True
