"""UsageService — запись raw событий + валидация + дневная агрегация + отчёты."""
import json
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func as sqlfn
from sqlalchemy.orm import Session

from app.models import UsageDaily, UsageEvent, UsageEventType, User


HEARTBEAT_SECONDS = 30


# Whitelist маршрутов SPA — нормализованные пути.
ALLOWED_PATHS: set[str] = {
    "/",
    "/projects",
    "/projects/:key",
    "/analytics",
    "/analytics/work-type-report",
    "/analytics/work-type-report/print",
    "/executive",
    "/sync",
    "/categories",
    "/capacity",
    "/backlog",
    "/planning",
    "/resource-planning",
    "/resource-planning/compare",
    "/settings",
    "/feedback",
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

    def _period(self, days: int) -> tuple[date_type, date_type]:
        end = date_type.today()
        start = end - timedelta(days=days - 1)
        return start, end

    def query_overview(self) -> dict:
        today = date_type.today()
        wk = today - timedelta(days=6)
        mo = today - timedelta(days=29)

        def _unique(since):
            return (
                self.db.query(UsageDaily.user_id)
                .filter(UsageDaily.date >= since)
                .distinct().count()
            )

        secs_30d = (
            self.db.query(sqlfn.coalesce(sqlfn.sum(UsageDaily.seconds), 0))
            .filter(UsageDaily.date >= mo)
            .scalar() or 0
        )
        return {
            "dau": _unique(today),
            "wau": _unique(wk),
            "mau": _unique(mo),
            "hours_30d": round(secs_30d / 3600, 1),
        }

    def query_users(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        rows = (
            self.db.query(
                User.id, User.display_name, User.role,
                sqlfn.count(sqlfn.distinct(UsageDaily.date)).label("active_days"),
                sqlfn.coalesce(sqlfn.sum(UsageDaily.seconds), 0).label("secs"),
                sqlfn.max(UsageDaily.date).label("last_date"),
            )
            .outerjoin(
                UsageDaily,
                (UsageDaily.user_id == User.id) & (UsageDaily.date >= start),
            )
            .group_by(User.id)
            .all()
        )

        path_rows = (
            self.db.query(
                UsageDaily.user_id,
                UsageDaily.path,
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.user_id, UsageDaily.path)
            .all()
        )
        top_per_user: dict[str, tuple[str, int]] = {}
        for pr in path_rows:
            secs = int(pr.secs or 0)
            cur = top_per_user.get(pr.user_id)
            if cur is None or secs > cur[1]:
                top_per_user[pr.user_id] = (pr.path, secs)

        return [{
            "user_id": r.id,
            "display_name": r.display_name,
            "role": r.role.value if hasattr(r.role, "value") else r.role,
            "last_seen": r.last_date,
            "active_days": int(r.active_days or 0),
            "hours": round((r.secs or 0) / 3600, 1),
            "top_path": top_per_user[r.id][0] if r.id in top_per_user else None,
        } for r in rows]

    def query_pages(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        rows = (
            self.db.query(
                UsageDaily.path,
                sqlfn.count(sqlfn.distinct(UsageDaily.user_id)).label("uu"),
                sqlfn.sum(UsageDaily.views).label("views"),
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.path)
            .all()
        )
        return [{
            "path": r.path,
            "unique_users": int(r.uu or 0),
            "views": int(r.views or 0),
            "hours": round((r.secs or 0) / 3600, 1),
        } for r in rows]

    def query_matrix(self, days: int = 30, top_n: int = 10) -> dict:
        start, _ = self._period(days)

        top_users = (
            self.db.query(UsageDaily.user_id, sqlfn.sum(UsageDaily.seconds).label("s"))
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.user_id)
            .order_by(sqlfn.sum(UsageDaily.seconds).desc())
            .limit(top_n).all()
        )
        user_ids = [u[0] for u in top_users]

        top_paths = (
            self.db.query(UsageDaily.path, sqlfn.sum(UsageDaily.seconds).label("s"))
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.path)
            .order_by(sqlfn.sum(UsageDaily.seconds).desc())
            .limit(top_n).all()
        )
        paths = [p[0] for p in top_paths]

        if not user_ids or not paths:
            return {"users": [], "paths": [], "cells": []}

        users_meta = {
            u.id: u.display_name for u in
            self.db.query(User).filter(User.id.in_(user_ids)).all()
        }

        cells_rows = (
            self.db.query(
                UsageDaily.user_id, UsageDaily.path,
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(
                UsageDaily.date >= start,
                UsageDaily.user_id.in_(user_ids),
                UsageDaily.path.in_(paths),
            )
            .group_by(UsageDaily.user_id, UsageDaily.path)
            .all()
        )
        return {
            "users": [{"user_id": uid, "display_name": users_meta.get(uid, uid)}
                      for uid in user_ids],
            "paths": [{"path": p} for p in paths],
            "cells": [{
                "user_id": r.user_id, "path": r.path,
                "display_name": users_meta.get(r.user_id, r.user_id),
                "hours": round((r.secs or 0) / 3600, 1),
            } for r in cells_rows],
        }

    def query_timeline(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        rows = (
            self.db.query(
                UsageDaily.date,
                sqlfn.sum(UsageDaily.views).label("views"),
                sqlfn.sum(UsageDaily.seconds).label("secs"),
                sqlfn.count(sqlfn.distinct(UsageDaily.user_id)).label("uu"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.date)
            .order_by(UsageDaily.date)
            .all()
        )
        return [{
            "date": r.date,
            "views": int(r.views or 0),
            "seconds": int(r.secs or 0),
            "active_users": int(r.uu or 0),
        } for r in rows]

    def query_actions(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        rows = (
            self.db.query(
                UsageEvent.action_type, UsageEvent.user_id,
                sqlfn.count().label("c"),
            )
            .filter(
                UsageEvent.event_type == UsageEventType.action,
                UsageEvent.at >= datetime.combine(start, datetime.min.time()),
            )
            .group_by(UsageEvent.action_type, UsageEvent.user_id)
            .all()
        )
        agg: dict[str, dict] = defaultdict(
            lambda: {"total": 0, "by_user": defaultdict(int)}
        )
        for r in rows:
            agg[r.action_type]["total"] += r.c
            agg[r.action_type]["by_user"][r.user_id] += r.c

        seen_user_ids = {uid for data in agg.values() for uid in data["by_user"].keys()}
        user_names = {
            u.id: u.display_name
            for u in self.db.query(User).filter(User.id.in_(seen_user_ids)).all()
        } if seen_user_ids else {}
        out = []
        for action_type, data in agg.items():
            top = sorted(data["by_user"].items(), key=lambda kv: -kv[1])[:3]
            out.append({
                "action_type": action_type,
                "total": data["total"],
                "top_users": [
                    {"user_id": uid, "display_name": user_names.get(uid, uid),
                     "count": cnt}
                    for uid, cnt in top
                ],
            })
        out.sort(key=lambda r: -r["total"])
        return out
