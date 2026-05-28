"""UsageService — запись raw событий + валидация + дневная агрегация."""
import json
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from app.models import UsageDaily, UsageEvent, UsageEventType


HEARTBEAT_SECONDS = 30


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

    def aggregate_day(self, target: date_type) -> int:
        """Свернуть raw события за `target` в usage_daily. Идемпотентно."""
        day_start = datetime.combine(target, datetime.min.time())
        day_end = day_start + timedelta(days=1)

        events = (
            self.db.query(UsageEvent)
            .filter(UsageEvent.at >= day_start, UsageEvent.at < day_end)
            .all()
        )
        buckets: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"views": 0, "seconds": 0, "actions": defaultdict(int)}
        )
        for ev in events:
            b = buckets[(ev.user_id, ev.path)]
            if ev.event_type == UsageEventType.page_view:
                b["views"] += 1
            elif ev.event_type == UsageEventType.heartbeat:
                b["seconds"] += HEARTBEAT_SECONDS
            elif ev.event_type == UsageEventType.action and ev.action_type:
                b["actions"][ev.action_type] += 1

        upserted = 0
        for (user_id, path), agg in buckets.items():
            existing = (
                self.db.query(UsageDaily)
                .filter_by(date=target, user_id=user_id, path=path)
                .one_or_none()
            )
            actions_json = json.dumps(dict(agg["actions"]))
            if existing is None:
                self.db.add(UsageDaily(
                    date=target, user_id=user_id, path=path,
                    views=agg["views"], seconds=agg["seconds"],
                    actions_json=actions_json,
                ))
            else:
                existing.views = agg["views"]
                existing.seconds = agg["seconds"]
                existing.actions_json = actions_json
            upserted += 1
        self.db.commit()
        return upserted

    def cleanup_old_events(self, retention_days: int = 90) -> int:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = (
            self.db.query(UsageEvent)
            .filter(UsageEvent.at < cutoff)
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return deleted
