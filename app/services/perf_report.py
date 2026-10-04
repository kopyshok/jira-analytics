"""Чтение замеров быстродействия за период — для экрана админа и выгрузок.

Агрегаты суммируются в базе (`GROUP BY`): каждый сброс пишет свои строки, и
несколько строк одной минуты и пути — нормальное состояние.

Вывод по медленному запросу (порядок проверки):
1. сервер загружен (≥ 85%), а наш процесс — малая доля (< 30% машины) —
   ресурсы занял кто-то другой;
2. больше половины времени запроса — обращения к базе — долгая работа с базой;
3. процессор нашего процесса был занят за время запроса (≥ 70% ядра) или
   в ту минуту (≥ 80% ядра) — медленный наш код;
4. иначе — ожидание: не процессор и не база (например, ответ Jira).

ponytail: снимки нескольких процессов (если сервис поедет в несколько
воркеров) усредняются вместе, а не складываются по процессу — при одном
воркере это одно и то же.
"""
from __future__ import annotations

import bisect
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.perf import HIST_SIZE, p95_from_hist
from app.models.perf import PERF_HIST_COLUMNS, PerfMinute, PerfServerSnapshot, PerfSlowRequest
from app.models.user import User

#: Период → (длина, размер точки графика в минутах).
PERIODS: dict[str, tuple[timedelta, int]] = {
    "1h": (timedelta(hours=1), 1),
    "24h": (timedelta(hours=24), 15),
    "7d": (timedelta(days=7), 60),
    "30d": (timedelta(days=30), 360),
}
PERIOD_LABELS = {
    "1h": "последний час",
    "24h": "последние сутки",
    "7d": "последние 7 дней",
    "30d": "последние 30 дней",
}

HOST_BUSY = 85.0
PROCESS_SMALL_SHARE = 30.0
DB_SHARE_HIGH = 0.5
REQUEST_CPU_HIGH = 70.0
PROCESS_CORE_HIGH = 80.0

VERDICT_LABELS = {
    "other_load": "Похоже, ресурсы сервера занял кто-то другой",
    "database": "Долгая работа с базой",
    "our_code": "Медленный наш код",
    "waiting": "Ожидание: не процессор и не база (например, ответ Jira)",
}

BOTTLENECKS_LIMIT = 50
SLOW_LIST_LIMIT = 200
SLOW_STATS_LIMIT = 10000

#: Первый сегмент пути после /api/v1/ → раздел, как он называется в меню.
SECTION_LABELS = {
    "admin": "Администрирование",
    "ai-status": "AI",
    "analytics": "Аналитика",
    "auth": "Вход",
    "backlog": "Целевые задачи",
    "capacity": "Ресурсы",
    "categories": "Категории работ",
    "desk": "Стол аналитика",
    "employees": "Сотрудники",
    "events": "Обновления на экране",
    "executive": "Сводка для руководителя",
    "exports": "Выгрузки",
    "feedback": "Обратная связь",
    "hierarchy-rules": "Правила иерархии",
    "issues": "Категории задач",
    "jira": "Синхронизация",
    "kpi": "KPI",
    "kpi-settings": "Настройки KPI",
    "llm": "AI",
    "mandatory-work-types": "Виды работ",
    "mapping": "Категории работ",
    "onboarding": "Первые шаги",
    "planning": "Сценарии",
    "production-calendar": "Производственный календарь",
    "projects": "Проекты",
    "release-notes": "Что нового",
    "resource-planning": "Ресурсное планирование",
    "roles": "Роли",
    "scope": "Проекты в scope",
    "settings": "Настройки",
    "sync": "Синхронизация",
    "team-desk": "Стол тимлида",
    "teams": "Команды",
    "themes": "Оформление",
    "ui-config": "Оформление",
    "usage": "Использование",
    "users": "Профиль",
    "work-desks": "Стол аналитика",
    "work-type-report": "Тематический отчёт",
}


def section_label(route: str) -> str:
    """Раздел по шаблону пути; незнакомый — первый сегмент как есть."""
    rest = route.split("/api/v1/", 1)[-1].lstrip("/")
    head = rest.split("/", 1)[0]
    return SECTION_LABELS.get(head, head or route)


def verdict(
    *,
    host_cpu: Optional[float],
    process_share: Optional[float],
    process_core: Optional[float],
    duration_ms: float,
    db_ms: float,
    cpu_ms: float,
) -> str:
    """Вероятная причина медленного запроса (см. порядок в описании модуля)."""
    if (
        host_cpu is not None and process_share is not None
        and host_cpu >= HOST_BUSY and process_share < PROCESS_SMALL_SHARE
    ):
        return "other_load"
    if duration_ms > 0 and db_ms / duration_ms >= DB_SHARE_HIGH:
        return "database"
    if duration_ms > 0 and cpu_ms / duration_ms * 100 >= REQUEST_CPU_HIGH:
        return "our_code"
    if process_core is not None and process_core >= PROCESS_CORE_HIGH:
        return "our_code"
    return "waiting"


def iso(dt: datetime) -> str:
    """Наивное UTC из базы → ISO с поясом, чтобы браузер не принял его за местное."""
    return dt.replace(tzinfo=timezone.utc).isoformat()


def _floor(dt: datetime, minutes: int) -> datetime:
    epoch = datetime(1970, 1, 1)
    step = minutes * 60
    seconds = int((dt - epoch).total_seconds()) // step * step
    return epoch + timedelta(seconds=seconds)


def _hist_sums() -> list[Any]:
    return [func.sum(getattr(PerfMinute, c)) for c in PERF_HIST_COLUMNS]


def _bottlenecks(db: Session, start: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = (
        db.query(
            PerfMinute.method, PerfMinute.route,
            func.sum(PerfMinute.count), func.sum(PerfMinute.total_ms), func.max(PerfMinute.max_ms),
            func.sum(PerfMinute.errors_5xx), func.sum(PerfMinute.db_count),
            func.sum(PerfMinute.db_ms), *_hist_sums(),
        )
        .filter(PerfMinute.minute >= start)
        .group_by(PerfMinute.method, PerfMinute.route)
        .all()
    )
    items = []
    total_hist = [0] * HIST_SIZE
    totals = {"requests": 0, "errors_5xx": 0, "total_ms": 0.0, "max_ms": 0.0}
    for method, route, count, total_ms, max_ms, errors, db_count, db_ms, *hist in rows:
        count, total_ms, max_ms = int(count or 0), float(total_ms or 0), float(max_ms or 0)
        if count <= 0:
            continue
        hist = [int(h or 0) for h in hist]
        total_hist = [a + b for a, b in zip(total_hist, hist)]
        totals["requests"] += count
        totals["errors_5xx"] += int(errors or 0)
        totals["total_ms"] += total_ms
        totals["max_ms"] = max(totals["max_ms"], max_ms)
        items.append({
            "method": method,
            "route": route,
            "section": section_label(route),
            "calls": count,
            "total_ms": total_ms,
            "avg_ms": total_ms / count,
            "p95_ms": p95_from_hist(hist, max_ms),
            "max_ms": max_ms,
            "errors_5xx": int(errors or 0),
            "db_avg_count": int(db_count or 0) / count,
            "db_share": float(db_ms or 0) / total_ms if total_ms > 0 else 0.0,
        })
    items.sort(key=lambda r: -r["total_ms"])
    totals["p95_ms"] = p95_from_hist(total_hist, totals["max_ms"])
    totals["avg_ms"] = totals["total_ms"] / totals["requests"] if totals["requests"] else 0.0
    return items[:BOTTLENECKS_LIMIT], totals


def _snapshots(db: Session, start: datetime) -> list[PerfServerSnapshot]:
    return (
        db.query(PerfServerSnapshot)
        .filter(PerfServerSnapshot.at >= start)
        .order_by(PerfServerSnapshot.at)
        .all()
    )


def _share(s: PerfServerSnapshot) -> float:
    """Доля процесса от всей машины, % — в тех же единицах, что загрузка сервера."""
    return s.process_cpu_percent / max(s.cpu_count, 1)


class _SnapshotIndex:
    """Поиск снимка, интервал которого покрывает момент запроса."""

    def __init__(self, snaps: list[PerfServerSnapshot], tolerance: timedelta) -> None:
        self.snaps = snaps
        self.ats = [s.at for s in snaps]
        self.tolerance = tolerance

    def find(self, at: datetime) -> Optional[PerfServerSnapshot]:
        i = bisect.bisect_left(self.ats, at)
        # Снимок пишется в конце интервала — сначала ближайший после запроса.
        if i < len(self.snaps) and self.ats[i] - at <= self.tolerance:
            return self.snaps[i]
        if i > 0 and at - self.ats[i - 1] <= self.tolerance:
            return self.snaps[i - 1]
        return None


def _load(snap: Optional[PerfServerSnapshot]) -> dict[str, Any]:
    if snap is None:
        return {
            "host_cpu": None, "process_cpu": None, "process_cpu_core": None,
            "host_memory": None, "process_memory_mb": None, "threads": None,
            "db_pool_in_use": None, "db_pool_size": None, "requests_in_flight": None,
        }
    return {
        "host_cpu": snap.host_cpu_percent,
        "process_cpu": _share(snap),
        "process_cpu_core": snap.process_cpu_percent,
        "host_memory": snap.host_memory_percent,
        "process_memory_mb": snap.process_memory_mb,
        "threads": snap.threads,
        "db_pool_in_use": snap.db_pool_in_use,
        "db_pool_size": snap.db_pool_size,
        "requests_in_flight": snap.requests_in_flight,
    }


def _verdict_for(slow: Any, snap: Optional[PerfServerSnapshot]) -> str:
    return verdict(
        host_cpu=snap.host_cpu_percent if snap else None,
        process_share=_share(snap) if snap else None,
        process_core=snap.process_cpu_percent if snap else None,
        duration_ms=slow.duration_ms,
        db_ms=slow.db_ms,
        cpu_ms=slow.cpu_ms,
    )


def overview(
    db: Session,
    period: str,
    *,
    now: Optional[datetime] = None,
    slow_ms: float,
    flush_seconds: float,
    slow_limit: int = SLOW_LIST_LIMIT,
) -> dict[str, Any]:
    """Всё для экрана за период: итог, ряд для графика, узкие места, медленные."""
    if period not in PERIODS:
        raise ValueError(f"Неизвестный период: {period}")
    length, bucket_minutes = PERIODS[period]
    now = now or datetime.utcnow()
    start = _floor(now - length, 1)
    bucket = timedelta(minutes=bucket_minutes)

    bottlenecks, totals = _bottlenecks(db, start)
    snaps = _snapshots(db, start)
    index = _SnapshotIndex(snaps, tolerance=timedelta(seconds=max(2 * flush_seconds, 120)))

    # --- ряд для графика: пустые точки тоже, чтобы ось времени была сплошной
    points: dict[datetime, dict[str, Any]] = {}
    t = _floor(start, bucket_minutes)
    while t <= now:
        points[t] = {"hist": [0] * HIST_SIZE, "count": 0, "max_ms": 0.0,
                     "host": [], "proc": [], "slow": Counter()}
        t += bucket

    def point(at: datetime) -> Optional[dict[str, Any]]:
        return points.get(_floor(at, bucket_minutes))

    per_minute = (
        db.query(PerfMinute.minute, func.sum(PerfMinute.count), func.max(PerfMinute.max_ms),
                 *_hist_sums())
        .filter(PerfMinute.minute >= start)
        .group_by(PerfMinute.minute)
        .all()
    )
    for minute, count, max_ms, *hist in per_minute:
        p = point(minute)
        if p is None:
            continue
        p["count"] += int(count or 0)
        p["max_ms"] = max(p["max_ms"], float(max_ms or 0))
        p["hist"] = [a + int(b or 0) for a, b in zip(p["hist"], hist)]
    for s in snaps:
        p = point(s.at)
        if p is not None:
            p["host"].append(s.host_cpu_percent)
            p["proc"].append(_share(s))

    # --- медленные: все за период для счёта причин, последние — с деталями
    slow_cols = (
        db.query(PerfSlowRequest.at, PerfSlowRequest.duration_ms, PerfSlowRequest.db_ms,
                 PerfSlowRequest.cpu_ms)
        .filter(PerfSlowRequest.at >= start)
        .order_by(PerfSlowRequest.at.desc())
        .limit(SLOW_STATS_LIMIT)
        .all()
    )
    verdicts: Counter = Counter()
    for s in slow_cols:
        v = _verdict_for(s, index.find(s.at))
        verdicts[v] += 1
        p = point(s.at)
        if p is not None:
            p["slow"][v] += 1

    series = []
    for t, p in points.items():
        top = p["slow"].most_common(1)
        series.append({
            "t": iso(t),
            "requests": p["count"],
            "p95_ms": p95_from_hist(p["hist"], p["max_ms"]) if p["count"] else None,
            "max_ms": p["max_ms"] if p["count"] else None,
            "slow": sum(p["slow"].values()),
            "host_cpu": sum(p["host"]) / len(p["host"]) if p["host"] else None,
            "host_cpu_max": max(p["host"]) if p["host"] else None,
            "process_cpu": sum(p["proc"]) / len(p["proc"]) if p["proc"] else None,
            "verdict": top[0][0] if top else None,
            "verdict_label": VERDICT_LABELS[top[0][0]] if top else None,
        })

    slow_rows = (
        db.query(PerfSlowRequest)
        .filter(PerfSlowRequest.at >= start)
        .order_by(PerfSlowRequest.at.desc())
        .limit(slow_limit)
        .all()
    )
    user_ids = {r.user_id for r in slow_rows if r.user_id}
    names = {
        u.id: (u.display_name or u.email)
        for u in db.query(User).filter(User.id.in_(user_ids)).all()
    } if user_ids else {}
    slow = []
    for r in slow_rows:
        snap = index.find(r.at)
        v = _verdict_for(r, snap)
        slow.append({
            "id": r.id,
            "at": iso(r.at),
            "method": r.method,
            "route": r.route,
            "section": section_label(r.route),
            "path": r.path,
            "query": r.query,
            "status_code": r.status_code,
            "duration_ms": r.duration_ms,
            "db_count": r.db_count,
            "db_ms": r.db_ms,
            "cpu_ms": r.cpu_ms,
            "user": names.get(r.user_id or ""),
            "top_queries": r.top_queries or [],
            **_load(snap),
            "verdict": v,
            "verdict_label": VERDICT_LABELS[v],
        })

    return {
        "period": period,
        "period_label": PERIOD_LABELS[period],
        "start": iso(start),
        "end": iso(now),
        "bucket_minutes": bucket_minutes,
        "slow_ms": slow_ms,
        "totals": {**totals, "slow": len(slow_cols)},
        "verdicts": dict(verdicts),
        "verdict_labels": VERDICT_LABELS,
        "series": series,
        "bottlenecks": bottlenecks,
        "slow": slow,
        "snapshots_count": len(snaps),
    }
