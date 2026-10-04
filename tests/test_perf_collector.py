"""Сборщик замеров быстродействия в памяти: минутные агрегаты, гистограмма, медленные."""
from datetime import datetime

import pytest

from app.core.perf import HIST_BOUNDS_MS, PerfCollector, hist_index, p95_from_hist

M1 = datetime(2026, 10, 4, 12, 0)
M2 = datetime(2026, 10, 4, 12, 1)


def _record(c: PerfCollector, **kw):
    base = dict(
        minute=M1, method="GET", route="/api/v1/backlog/{item_id}",
        duration_ms=10.0, status=200, db_count=0, db_ms=0.0, slow=None,
    )
    base.update(kw)
    c.record(**base)


def test_hist_index_puts_duration_into_bucket():
    assert hist_index(0) == 0
    assert hist_index(HIST_BOUNDS_MS[0]) == 0  # граница включительно
    assert hist_index(HIST_BOUNDS_MS[0] + 0.1) == 1
    assert hist_index(10 ** 9) == len(HIST_BOUNDS_MS)  # хвост сверх последней границы


def test_p95_interpolates_inside_bucket_and_caps_by_max():
    hist = [0] * (len(HIST_BOUNDS_MS) + 1)
    assert p95_from_hist(hist, max_ms=0) == 0
    # 100 запросов в корзине (100, 200] → 95-й процентиль внутри корзины
    i = hist_index(150)
    hist[i] = 100
    p95 = p95_from_hist(hist, max_ms=180)
    assert HIST_BOUNDS_MS[i - 1] < p95 <= 180
    # хвост сверх последней границы ограничен максимумом
    tail = [0] * (len(HIST_BOUNDS_MS) + 1)
    tail[-1] = 10
    assert p95_from_hist(tail, max_ms=45000) <= 45000


def test_record_accumulates_minute_bucket_per_route():
    c = PerfCollector(enabled=True, slow_ms=2000)
    _record(c, duration_ms=10, db_count=2, db_ms=3)
    _record(c, duration_ms=30, db_count=1, db_ms=1, status=500)
    _record(c, duration_ms=5, method="POST")
    _record(c, duration_ms=7, minute=M2)

    aggs, slow = c.drain()
    assert slow == []
    a = aggs[(M1, "GET", "/api/v1/backlog/{item_id}")]
    assert a.count == 2
    assert a.total_ms == pytest.approx(40)
    assert a.max_ms == pytest.approx(30)
    assert a.errors_5xx == 1
    assert a.db_count == 3
    assert a.db_ms == pytest.approx(4)
    assert sum(a.hist) == 2
    assert (M1, "POST", "/api/v1/backlog/{item_id}") in aggs
    assert (M2, "GET", "/api/v1/backlog/{item_id}") in aggs


def test_drain_empties_buffers():
    c = PerfCollector(enabled=True, slow_ms=2000)
    _record(c, slow={"path": "/x"})
    aggs, slow = c.drain()
    assert len(aggs) == 1 and len(slow) == 1
    assert c.drain() == ({}, [])


def test_slow_buffer_is_capped():
    c = PerfCollector(enabled=True, slow_ms=2000, max_slow_buffer=3)
    for i in range(5):
        _record(c, slow={"n": i})
    _, slow = c.drain()
    assert [s["n"] for s in slow] == [0, 1, 2]


def test_in_flight_peak_resets_after_read():
    c = PerfCollector(enabled=True, slow_ms=2000)
    c.request_started()
    c.request_started()
    c.request_finished()
    assert c.in_flight == 1
    assert c.take_in_flight_peak() == 2
    # после чтения пик начинается с текущего значения
    assert c.take_in_flight_peak() == 1


def test_drain_before_keeps_current_minute():
    """Сбрасываются только закрытые минуты; текущая копится до своего конца."""
    c = PerfCollector(enabled=True, slow_ms=2000)
    _record(c, minute=M1, slow={"n": 1})
    _record(c, minute=M2)

    aggs, slow = c.drain(before=M2)
    assert [k[0] for k in aggs] == [M1]
    assert len(slow) == 1

    aggs, slow = c.drain()
    assert [k[0] for k in aggs] == [M2]
    assert slow == []
