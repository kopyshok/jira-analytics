"""Замеры быстродействия в памяти процесса — источник для раздела «Быстродействие».

Каждый запрос к API складывается в агрегат «минута × метод × шаблон пути»: число,
сумма и максимум длительности, гистограмма по корзинам (из неё — 95-й процентиль),
ошибки 5xx, обращения к базе. Медленные запросы копятся отдельно, с деталями.
Фоновый цикл (`app/services/perf_writer.py`) раз в минуту забирает всё через
`drain()` и пишет в базу одной пачкой.

Обращения к базе считаются событиями SQLAlchemy на классе `Engine`: статистику
запроса кладёт промежуточный слой в `contextvars`, поток пула FastAPI видит её
через копию контекста. Вне запроса (фоновые задачи, синк) счётчик молчит.
"""
from __future__ import annotations

import bisect
import threading
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Optional

from sqlalchemy import event
from sqlalchemy.engine import Engine

#: Верхние границы корзин гистограммы, мс (включительно). Последняя корзина —
#: всё, что дольше последней границы. Число корзин = len(HIST_BOUNDS_MS) + 1.
HIST_BOUNDS_MS: tuple[float, ...] = (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000)
HIST_SIZE = len(HIST_BOUNDS_MS) + 1

#: Сколько самых долгих обращений к базе хранить у медленного запроса.
TOP_QUERIES = 5
#: Длина текста обращения к базе в деталях медленного запроса.
SQL_MAX_CHARS = 500


def hist_index(duration_ms: float) -> int:
    """Номер корзины гистограммы для длительности."""
    return bisect.bisect_left(HIST_BOUNDS_MS, duration_ms)


def p95_from_hist(hist: list[int], max_ms: float, q: float = 0.95) -> float:
    """Оценка процентиля по гистограмме: линейно внутри корзины, не выше максимума."""
    total = sum(hist)
    if total <= 0:
        return 0.0
    target = q * total
    cum = 0
    for i, n in enumerate(hist):
        if n <= 0:
            continue
        if cum + n >= target:
            lower = HIST_BOUNDS_MS[i - 1] if i > 0 else 0.0
            upper = HIST_BOUNDS_MS[i] if i < len(HIST_BOUNDS_MS) else max(max_ms, lower)
            value = lower + (upper - lower) * (target - cum) / n
            return min(value, max_ms) if max_ms > 0 else value
        cum += n
    return max_ms


@dataclass
class MinuteAgg:
    """Агрегат запросов одного шаблона пути за минуту."""

    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    hist: list[int] = field(default_factory=lambda: [0] * HIST_SIZE)
    errors_5xx: int = 0
    db_count: int = 0
    db_ms: float = 0.0


AggKey = tuple[datetime, str, str]


class PerfCollector:
    """Агрегаты и медленные запросы до очередного сброса в базу.

    Пишет промежуточный слой (поток событийного цикла), забирает фоновый цикл
    из рабочего потока — отсюда блокировка.
    """

    def __init__(self, *, enabled: bool, slow_ms: float, max_slow_buffer: int = 500) -> None:
        self.enabled = enabled
        self.slow_ms = slow_ms
        self.max_slow_buffer = max_slow_buffer
        self._lock = threading.Lock()
        self._aggs: dict[AggKey, MinuteAgg] = {}
        self._slow: list[dict[str, Any]] = []
        self.in_flight = 0
        self._in_flight_peak = 0

    def record(
        self,
        *,
        minute: datetime,
        method: str,
        route: str,
        duration_ms: float,
        status: int,
        db_count: int,
        db_ms: float,
        slow: Optional[dict[str, Any]],
    ) -> None:
        with self._lock:
            agg = self._aggs.get((minute, method, route))
            if agg is None:
                agg = self._aggs[(minute, method, route)] = MinuteAgg()
            agg.count += 1
            agg.total_ms += duration_ms
            agg.max_ms = max(agg.max_ms, duration_ms)
            agg.hist[hist_index(duration_ms)] += 1
            if status >= 500:
                agg.errors_5xx += 1
            agg.db_count += db_count
            agg.db_ms += db_ms
            # Шторм медленных при недоступной базе не должен съесть память.
            if slow is not None and len(self._slow) < self.max_slow_buffer:
                self._slow.append(slow)

    def drain(
        self, before: Optional[datetime] = None,
    ) -> tuple[dict[AggKey, MinuteAgg], list[dict[str, Any]]]:
        """Забрать накопленное. С `before` — только закрытые минуты (раньше неё);
        текущая минута копится дальше, чтобы в базе была одна строка на минуту и путь.
        Медленные забираются все — у каждого своя строка."""
        with self._lock:
            slow, self._slow = self._slow, []
            if before is None:
                aggs, self._aggs = self._aggs, {}
            else:
                aggs = {k: a for k, a in self._aggs.items() if k[0] < before}
                self._aggs = {k: a for k, a in self._aggs.items() if k[0] >= before}
        return aggs, slow

    def request_started(self) -> None:
        with self._lock:
            self.in_flight += 1
            self._in_flight_peak = max(self._in_flight_peak, self.in_flight)

    def request_finished(self) -> None:
        with self._lock:
            self.in_flight -= 1

    def take_in_flight_peak(self) -> int:
        """Пик запросов в работе с прошлого снимка; дальше пик считается от текущего."""
        with self._lock:
            peak = self._in_flight_peak
            self._in_flight_peak = self.in_flight
        return peak


# --- Счётчик обращений к базе в рамках запроса -------------------------------


class RequestStats:
    """Обращения к базе одного запроса: число, время, самые долгие."""

    __slots__ = ("db_count", "db_ms", "top", "closed")

    def __init__(self) -> None:
        self.db_count = 0
        self.db_ms = 0.0
        self.top: list[tuple[float, str]] = []
        self.closed = False

    def add_query(self, statement: str, ms: float) -> None:
        if self.closed:
            return
        self.db_count += 1
        self.db_ms += ms
        if len(self.top) < TOP_QUERIES:
            self.top.append((ms, statement))
            return
        low = min(range(len(self.top)), key=lambda i: self.top[i][0])
        if ms > self.top[low][0]:
            self.top[low] = (ms, statement)

    def top_queries(self) -> list[dict[str, Any]]:
        """Самые долгие обращения: текст без значений параметров, обрезан."""
        return [
            {"ms": round(ms, 1), "sql": " ".join(sql.split())[:SQL_MAX_CHARS]}
            for ms, sql in sorted(self.top, key=lambda x: -x[0])
        ]


current_stats: ContextVar[Optional[RequestStats]] = ContextVar("perf_request_stats", default=None)

_T0_ATTR = "_perf_t0"


def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    if context is not None and current_stats.get() is not None:
        setattr(context, _T0_ATTR, perf_counter())


def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
    stats = current_stats.get()
    if stats is None or context is None:
        return
    t0 = getattr(context, _T0_ATTR, None)
    if t0 is None:
        return
    # Текст обращения хранится с плейсхолдерами — значения параметров не берём.
    stats.add_query(statement, (perf_counter() - t0) * 1000)


def install_query_listeners() -> None:
    """Подписаться на события всех движков. Повторный вызов ничего не меняет."""
    if not event.contains(Engine, "before_cursor_execute", _before_cursor_execute):
        event.listen(Engine, "before_cursor_execute", _before_cursor_execute)
    if not event.contains(Engine, "after_cursor_execute", _after_cursor_execute):
        event.listen(Engine, "after_cursor_execute", _after_cursor_execute)
