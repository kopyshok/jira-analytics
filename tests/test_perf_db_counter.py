"""Счётчик обращений к базе в рамках запроса (события SQLAlchemy + contextvars)."""
import asyncio

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from app.core import perf
from app.core.perf import RequestStats, current_stats, install_query_listeners


@pytest.fixture(autouse=True)
def _remove_listeners_after():
    """Слушатели глобальные — после теста снимаем, чтобы не трогать остальной прогон."""
    yield
    for name, fn in (
        ("before_cursor_execute", perf._before_cursor_execute),
        ("after_cursor_execute", perf._after_cursor_execute),
    ):
        if event.contains(Engine, name, fn):
            event.remove(Engine, name, fn)


def _engine():
    install_query_listeners()
    install_query_listeners()  # повторный вызов не задваивает счёт
    return create_engine("sqlite:///:memory:")


def test_queries_outside_request_are_not_counted():
    eng = _engine()
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert current_stats.get() is None


def test_queries_inside_request_are_counted_without_parameter_values():
    eng = _engine()
    stats = RequestStats()
    token = current_stats.set(stats)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT :secret_value"), {"secret_value": "пароль-123"})
    finally:
        current_stats.reset(token)

    assert stats.db_count == 2
    assert stats.db_ms >= 0
    top = stats.top_queries()
    assert len(top) == 2
    assert all("пароль-123" not in q["sql"] for q in top)
    assert any("secret_value" in q["sql"] or "?" in q["sql"] for q in top)


def test_top_keeps_five_longest_and_truncates_text():
    stats = RequestStats()
    for i in range(8):
        stats.add_query("SELECT " + "x" * 1000, float(i))
    top = stats.top_queries()
    assert [q["ms"] for q in top] == [7.0, 6.0, 5.0, 4.0, 3.0]
    assert all(len(q["sql"]) <= 500 for q in top)


def test_closed_stats_ignore_late_queries():
    stats = RequestStats()
    stats.closed = True
    stats.add_query("SELECT 1", 5.0)
    assert stats.db_count == 0


def test_counts_queries_from_worker_thread():
    """Синхронный эндпоинт FastAPI крутится в пуле потоков с копией контекста."""
    eng = _engine()
    stats = RequestStats()

    def work():
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))

    async def main():
        token = current_stats.set(stats)
        try:
            await asyncio.to_thread(work)
        finally:
            current_stats.reset(token)

    asyncio.run(main())
    assert stats.db_count == 1


def test_engine_created_before_install_is_counted():
    """Движок приложения создаётся при импорте, слушатели ставятся позже — в `main`."""
    eng = create_engine("sqlite:///:memory:")
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))  # пул уже живой
        install_query_listeners()
        stats = RequestStats()
        token = current_stats.set(stats)
        try:
            conn.execute(text("SELECT 2"))
        finally:
            current_stats.reset(token)
    assert stats.db_count == 1
