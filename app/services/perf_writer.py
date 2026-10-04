"""Фоновая запись замеров быстродействия в базу.

Раз в `perf_flush_seconds`: забрать агрегаты и медленные из сборщика и записать
пачкой, снять нагрузку сервера (`psutil`), раз в час — удалить записи старше
`perf_retention_days`. Работа с базой — в рабочем потоке, чтобы не держать
событийный цикл. Любая ошибка — в лог и пропуск: замеры не важнее запросов.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import psutil  # type: ignore[import-untyped]
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.perf import AggKey, MinuteAgg, PerfCollector
from app.models.perf import PerfMinute, PerfServerSnapshot, PerfSlowRequest

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
CLEANUP_EVERY = timedelta(hours=1)


def flush(
    session_factory: SessionFactory,
    aggs: dict[AggKey, MinuteAgg],
    slow: list[dict[str, Any]],
) -> None:
    """Записать агрегаты и медленные запросы одной пачкой."""
    if not aggs and not slow:
        return
    db = session_factory()
    try:
        db.add_all(
            PerfMinute(
                minute=minute, method=method, route=route[:300],
                count=a.count, total_ms=a.total_ms, max_ms=a.max_ms,
                errors_5xx=a.errors_5xx, db_count=a.db_count, db_ms=a.db_ms,
                **{f"h{i}": n for i, n in enumerate(a.hist)},
            )
            for (minute, method, route), a in aggs.items()
        )
        db.add_all(PerfSlowRequest(**{**s, "route": s["route"][:300]}) for s in slow)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("perf: не удалось записать замеры (%d агрегатов, %d медленных): %s",
                       len(aggs), len(slow), exc)
    finally:
        db.close()


class ServerProbe:
    """Нагрузка сервера между двумя вызовами `read()`.

    Первый замер процессора у `psutil` бессмыслен (0.0) — пробный вызов делается
    в конструкторе, дальше каждый вызов отдаёт загрузку с прошлого.
    """

    def __init__(self) -> None:
        self.proc = psutil.Process()
        psutil.cpu_percent(None)
        self.proc.cpu_percent(None)

    def read(self) -> dict[str, Any]:
        return {
            "host_cpu_percent": psutil.cpu_percent(None),
            "host_memory_percent": psutil.virtual_memory().percent,
            "process_cpu_percent": self.proc.cpu_percent(None),
            "process_memory_mb": self.proc.memory_info().rss / (1024 * 1024),
            "cpu_count": psutil.cpu_count() or 1,
            "threads": self.proc.num_threads(),
        }


def _pool_usage(engine: Optional[Engine]) -> tuple[Optional[int], Optional[int]]:
    """Занятые и всего подключений пула. У пулов без очереди (SQLite в памяти) — нет данных."""
    try:
        pool: Any = engine.pool  # type: ignore[union-attr]
        in_use = pool.checkedout()
        total = pool.size() + max(getattr(pool, "_max_overflow", 0), 0)
        return int(in_use), int(total)
    except Exception:
        return None, None


def take_snapshot(
    session_factory: SessionFactory,
    probe: ServerProbe,
    *,
    engine: Optional[Engine],
    in_flight: int,
) -> None:
    """Записать снимок нагрузки сервера."""
    db = session_factory()
    try:
        in_use, total = _pool_usage(engine)
        db.add(PerfServerSnapshot(
            at=datetime.utcnow(), db_pool_in_use=in_use, db_pool_size=total,
            requests_in_flight=in_flight, **probe.read(),
        ))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("perf: не удалось записать снимок сервера: %s", exc)
    finally:
        db.close()


def cleanup(session_factory: SessionFactory, *, retention_days: int, now: datetime) -> None:
    """Удалить замеры старше срока хранения."""
    cutoff = now - timedelta(days=retention_days)
    db = session_factory()
    try:
        db.query(PerfMinute).filter(PerfMinute.minute < cutoff).delete(synchronize_session=False)
        db.query(PerfSlowRequest).filter(PerfSlowRequest.at < cutoff).delete(synchronize_session=False)
        db.query(PerfServerSnapshot).filter(PerfServerSnapshot.at < cutoff).delete(
            synchronize_session=False,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("perf: не удалось удалить старые замеры: %s", exc)
    finally:
        db.close()


def flush_collector(collector: PerfCollector, session_factory: SessionFactory) -> None:
    """Сбросить накопленное — на остановке сервиса, чтобы не терять последнюю минуту."""
    flush(session_factory, *collector.drain())


async def run_loop(
    collector: PerfCollector,
    *,
    interval: float,
    retention_days: int,
    session_factory: SessionFactory,
    engine: Optional[Engine],
) -> None:
    """Бесконечный цикл записи; останавливается отменой задачи."""
    probe = await asyncio.to_thread(ServerProbe)
    last_cleanup: Optional[datetime] = None

    def tick() -> None:
        nonlocal last_cleanup
        flush(session_factory, *collector.drain())
        take_snapshot(
            session_factory, probe, engine=engine, in_flight=collector.take_in_flight_peak(),
        )
        now = datetime.utcnow()
        if last_cleanup is None or now - last_cleanup >= CLEANUP_EVERY:
            cleanup(session_factory, retention_days=retention_days, now=now)
            last_cleanup = now

    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(tick)
        except Exception:  # страховка: цикл не должен умирать
            logger.exception("perf: сбой цикла записи замеров")
