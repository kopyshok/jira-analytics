"""Фоновая запись замеров: сброс агрегатов, снимок сервера, чистка, цикл."""
import asyncio
import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.perf import PerfCollector, hist_index
from app.models.perf import PerfMinute, PerfServerSnapshot, PerfSlowRequest
from app.services import perf_writer
from app.services.perf_writer import ServerProbe, cleanup, flush, run_loop, take_snapshot

NOW = datetime(2026, 10, 4, 12, 30)


@pytest.fixture
def factory(engine, db_session):
    """Фабрика сессий на тестовом движке; db_session нужен ради чистки таблиц после теста."""
    return sessionmaker(bind=engine, autoflush=False)


def _slow(**kw):
    base = dict(
        at=NOW, method="GET", route="/api/v1/x/{id}", path="/api/v1/x/1", query="a=1",
        status_code=200, duration_ms=2500.0, db_count=3, db_ms=1200.0, cpu_ms=300.0,
        user_id=None, top_queries=[{"ms": 1000.0, "sql": "SELECT 1"}],
    )
    base.update(kw)
    return base


def test_flush_writes_aggregates_and_slow(factory, db_session):
    c = PerfCollector(enabled=True, slow_ms=2000)
    minute = NOW.replace(second=0)
    for ms in (10, 30, 2500):
        c.record(minute=minute, method="GET", route="/api/v1/x/{id}", duration_ms=ms,
                 status=200, db_count=1, db_ms=2, slow=_slow() if ms > 2000 else None)
    aggs, slow = c.drain()

    flush(factory, aggs, slow)

    [row] = db_session.query(PerfMinute).all()
    assert (row.minute, row.method, row.route, row.count) == (minute, "GET", "/api/v1/x/{id}", 3)
    assert row.total_ms == pytest.approx(2540)
    assert row.max_ms == pytest.approx(2500)
    assert row.db_count == 3
    assert getattr(row, f"h{hist_index(2500)}") == 1
    [s] = db_session.query(PerfSlowRequest).all()
    assert s.top_queries == [{"ms": 1000.0, "sql": "SELECT 1"}]
    assert s.cpu_ms == pytest.approx(300)


def test_flush_swallows_db_errors(caplog):
    broken = sessionmaker(bind=create_engine("sqlite:///:memory:"))  # таблиц нет
    c = PerfCollector(enabled=True, slow_ms=2000)
    c.record(minute=NOW, method="GET", route="/r", duration_ms=1, status=200,
             db_count=0, db_ms=0, slow=None)
    with caplog.at_level(logging.WARNING, logger=perf_writer.__name__):
        flush(broken, *c.drain())  # не бросает
    assert "perf" in caplog.text


def test_take_snapshot_writes_server_load(factory, db_session, engine):
    probe = ServerProbe()
    take_snapshot(factory, probe, engine=engine, in_flight=4)
    [snap] = db_session.query(PerfServerSnapshot).all()
    assert snap.cpu_count >= 1
    assert snap.threads >= 1
    assert snap.process_memory_mb > 0
    assert 0 <= snap.host_cpu_percent <= 100
    assert snap.requests_in_flight == 4


def test_cleanup_drops_rows_older_than_retention(factory, db_session):
    old, fresh = NOW - timedelta(days=31), NOW - timedelta(days=29)
    for at in (old, fresh):
        db_session.add(PerfMinute(minute=at, method="GET", route="/r", count=1))
        db_session.add(PerfSlowRequest(**_slow(at=at)))
        db_session.add(PerfServerSnapshot(
            at=at, host_cpu_percent=1, host_memory_percent=1, process_cpu_percent=1,
            process_memory_mb=1, cpu_count=1, threads=1,
        ))
    db_session.commit()

    cleanup(factory, retention_days=30, now=NOW)

    db_session.expire_all()
    assert [r.minute for r in db_session.query(PerfMinute).all()] == [fresh]
    assert [r.at for r in db_session.query(PerfSlowRequest).all()] == [fresh]
    assert [r.at for r in db_session.query(PerfServerSnapshot).all()] == [fresh]


def test_run_loop_flushes_and_snapshots_until_cancelled(factory, db_session, engine):
    c = PerfCollector(enabled=True, slow_ms=2000)
    c.record(minute=NOW, method="GET", route="/r", duration_ms=1, status=200,
             db_count=0, db_ms=0, slow=None)

    async def main():
        task = asyncio.create_task(run_loop(
            c, interval=0.05, retention_days=30, session_factory=factory, engine=engine,
        ))
        await asyncio.sleep(0.4)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    db_session.expire_all()
    assert db_session.query(PerfMinute).count() == 1
    assert db_session.query(PerfServerSnapshot).count() >= 1
