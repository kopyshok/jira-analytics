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

    def _today_raw_buckets(self) -> dict[tuple[str, str], dict]:
        """Сегодняшний срез raw событий, сгруппированный (user_id, path).

        Нужен потому что usage_daily наполняется ночным cron-ом —
        в течение дня данные за сегодня живут только в usage_events.
        """
        today = date_type.today()
        day_start = datetime.combine(today, datetime.min.time())
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
        return buckets

    def query_overview(self) -> dict:
        today = date_type.today()
        wk = today - timedelta(days=6)
        mo = today - timedelta(days=29)

        def _unique_daily(since: date_type) -> set[str]:
            return {
                r[0] for r in
                self.db.query(UsageDaily.user_id)
                .filter(UsageDaily.date >= since)
                .distinct().all()
            }

        today_buckets = self._today_raw_buckets()
        today_users_raw = {uid for (uid, _) in today_buckets}
        today_users_daily = {
            r[0] for r in
            self.db.query(UsageDaily.user_id)
            .filter(UsageDaily.date == today)
            .distinct().all()
        }
        today_users = today_users_raw | today_users_daily
        today_secs_raw = sum(b["seconds"] for b in today_buckets.values())

        return {
            "dau": len(today_users),
            "wau": len(_unique_daily(wk) | today_users),
            "mau": len(_unique_daily(mo) | today_users),
            "hours_30d": round((
                (self.db.query(sqlfn.coalesce(sqlfn.sum(UsageDaily.seconds), 0))
                    .filter(UsageDaily.date >= mo).scalar() or 0)
                + today_secs_raw
            ) / 3600, 1),
        }

    def query_users(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        today = date_type.today()
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

        today_buckets = self._today_raw_buckets()
        today_secs_per_user: dict[str, int] = defaultdict(int)
        today_users: set[str] = set()
        for (uid, path), b in today_buckets.items():
            today_users.add(uid)
            today_secs_per_user[uid] += b["seconds"]
            cur = top_per_user.get(uid)
            if cur is None or b["seconds"] > cur[1]:
                top_per_user[uid] = (path, b["seconds"])

        return [{
            "user_id": r.id,
            "display_name": r.display_name,
            "role": r.role.value if hasattr(r.role, "value") else r.role,
            "last_seen": today if r.id in today_users else r.last_date,
            "active_days": int(r.active_days or 0) + (1 if r.id in today_users else 0),
            "hours": round(((r.secs or 0) + today_secs_per_user.get(r.id, 0)) / 3600, 1),
            "top_path": top_per_user[r.id][0] if r.id in top_per_user else None,
        } for r in rows]

    def query_pages(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        rows = (
            self.db.query(
                UsageDaily.path,
                sqlfn.sum(UsageDaily.views).label("views"),
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.path)
            .all()
        )
        users_per_path: dict[str, set[str]] = defaultdict(set)
        for r in self.db.query(UsageDaily.path, UsageDaily.user_id).filter(
            UsageDaily.date >= start,
        ).distinct().all():
            users_per_path[r.path].add(r.user_id)

        agg: dict[str, dict] = {
            r.path: {
                "views": int(r.views or 0),
                "seconds": int(r.secs or 0),
                "users": set(users_per_path.get(r.path, set())),
            } for r in rows
        }
        for (uid, path), b in self._today_raw_buckets().items():
            slot = agg.setdefault(path, {"views": 0, "seconds": 0, "users": set()})
            slot["views"] += b["views"]
            slot["seconds"] += b["seconds"]
            slot["users"].add(uid)

        return [{
            "path": path,
            "unique_users": len(d["users"]),
            "views": d["views"],
            "hours": round(d["seconds"] / 3600, 1),
        } for path, d in agg.items()]

    def query_matrix(self, days: int = 30, top_n: int = 10) -> dict:
        start, _ = self._period(days)

        cells: dict[tuple[str, str], int] = defaultdict(int)
        for r in (
            self.db.query(
                UsageDaily.user_id, UsageDaily.path,
                sqlfn.sum(UsageDaily.seconds).label("secs"),
            )
            .filter(UsageDaily.date >= start)
            .group_by(UsageDaily.user_id, UsageDaily.path)
            .all()
        ):
            cells[(r.user_id, r.path)] += int(r.secs or 0)
        for (uid, path), b in self._today_raw_buckets().items():
            cells[(uid, path)] += b["seconds"]

        if not cells:
            return {"users": [], "paths": [], "cells": []}

        user_totals: dict[str, int] = defaultdict(int)
        path_totals: dict[str, int] = defaultdict(int)
        for (uid, path), s in cells.items():
            user_totals[uid] += s
            path_totals[path] += s

        user_ids = [u for u, _ in sorted(user_totals.items(), key=lambda kv: -kv[1])[:top_n]]
        paths = [p for p, _ in sorted(path_totals.items(), key=lambda kv: -kv[1])[:top_n]]
        user_set = set(user_ids)
        path_set = set(paths)

        users_meta = {
            u.id: u.display_name for u in
            self.db.query(User).filter(User.id.in_(user_ids)).all()
        }

        return {
            "users": [{"user_id": uid, "display_name": users_meta.get(uid, uid)}
                      for uid in user_ids],
            "paths": [{"path": p} for p in paths],
            "cells": [{
                "user_id": uid, "path": path,
                "display_name": users_meta.get(uid, uid),
                "hours": round(s / 3600, 1),
            } for (uid, path), s in cells.items()
              if uid in user_set and path in path_set],
        }

    def query_timeline(self, days: int = 30) -> list[dict]:
        start, _ = self._period(days)
        today = date_type.today()
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
        out_by_date: dict[date_type, dict] = {
            r.date: {
                "views": int(r.views or 0),
                "seconds": int(r.secs or 0),
                "active_users": int(r.uu or 0),
            } for r in rows
        }

        today_buckets = self._today_raw_buckets()
        if today_buckets:
            today_views = sum(b["views"] for b in today_buckets.values())
            today_secs = sum(b["seconds"] for b in today_buckets.values())
            today_uu = len({uid for (uid, _) in today_buckets})
            out_by_date[today] = {
                "views": out_by_date.get(today, {}).get("views", 0) + today_views,
                "seconds": out_by_date.get(today, {}).get("seconds", 0) + today_secs,
                "active_users": max(
                    out_by_date.get(today, {}).get("active_users", 0), today_uu,
                ),
            }

        return [{
            "date": d,
            "views": v["views"],
            "seconds": v["seconds"],
            "active_users": v["active_users"],
        } for d, v in sorted(out_by_date.items())]

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
