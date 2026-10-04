"""Замеры быстродействия: минутные агрегаты, медленные запросы, снимки сервера.

Хранятся `perf_retention_days` (30 дней), чистит фоновый цикл
`app/services/perf_writer.py`. Время — наивное UTC, как `TimestampMixin`.

Каждый сброс пишет свои строки, без слияния с прошлыми: если сервис поедет в
несколько процессов, их строки не конфликтуют, а чтение их суммирует.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class PerfMinute(Base, TimestampMixin):
    """Агрегат запросов одного шаблона пути за минуту.

    Корзины гистограммы `h0..h10` — отдельные колонки, а не JSON: так период
    в 30 дней суммируется одним GROUP BY в базе. Границы корзин —
    `app.core.perf.HIST_BOUNDS_MS` (последняя корзина — всё, что дольше).
    """

    __tablename__ = "perf_minute"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    minute: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str] = mapped_column(String(300), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    errors_5xx: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    db_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    db_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    h0: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h1: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h2: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h3: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h4: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h5: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h6: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h7: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h8: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h9: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    h10: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_perf_minute_minute", "minute"),
        Index("ix_perf_minute_route_minute", "route", "minute"),
    )


#: Имена колонок корзин гистограммы по порядку.
PERF_HIST_COLUMNS = tuple(f"h{i}" for i in range(11))


class PerfSlowRequest(Base, TimestampMixin):
    """Медленный запрос с деталями. Тела запроса и секретов тут нет."""

    __tablename__ = "perf_slow_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    route: Mapped[str] = mapped_column(String(300), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    db_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    db_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Процессорное время нашего процесса за время запроса (все потоки).
    cpu_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    #: Без внешнего ключа: запись замера не должна падать из-за удалённого пользователя.
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    #: [{"ms": float, "sql": str}] — до 5 самых долгих обращений, без значений параметров.
    top_queries: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    __table_args__ = (Index("ix_perf_slow_request_at", "at"),)


class PerfServerSnapshot(Base, TimestampMixin):
    """Нагрузка сервера за интервал между снимками (обычно минута).

    Процессор процесса — как его отдаёт `psutil`: 100 = одно ядро целиком;
    долю от всей машины даёт деление на `cpu_count`.
    """

    __tablename__ = "perf_server_snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    host_cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    host_memory_percent: Mapped[float] = mapped_column(Float, nullable=False)
    process_cpu_percent: Mapped[float] = mapped_column(Float, nullable=False)
    process_memory_mb: Mapped[float] = mapped_column(Float, nullable=False)
    cpu_count: Mapped[int] = mapped_column(Integer, nullable=False)
    threads: Mapped[int] = mapped_column(Integer, nullable=False)
    db_pool_in_use: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    db_pool_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    #: Пик одновременных запросов к API за интервал.
    requests_in_flight: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_perf_server_snapshot_at", "at"),)
