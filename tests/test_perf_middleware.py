"""Промежуточный слой замеров: что и как попадает в сборщик."""
import time
from datetime import datetime

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine

from app.core import perf
from app.core.perf import PerfCollector, install_query_listeners
from app.core.perf_middleware import PerfMiddleware, sanitize_query


@pytest.fixture(autouse=True)
def _remove_listeners_after():
    yield
    for name, fn in (
        ("before_cursor_execute", perf._before_cursor_execute),
        ("after_cursor_execute", perf._after_cursor_execute),
    ):
        if event.contains(Engine, name, fn):
            event.remove(Engine, name, fn)


def _app(collector: PerfCollector) -> TestClient:
    app = FastAPI()
    eng = create_engine("sqlite:///:memory:")

    @app.get("/api/v1/items/{item_id}")
    def get_item(item_id: str) -> dict:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"id": item_id}

    @app.get("/api/v1/boom")
    def boom() -> None:
        raise RuntimeError("сбой")

    @app.get("/api/v1/admin/perf/overview")
    def own() -> dict:
        return {}

    @app.get("/health")
    def health() -> dict:
        return {}

    @app.get("/api/v1/stream")
    def stream() -> StreamingResponse:
        def events():
            # Заголовки уже ушли — поток не должен числиться «запросом в работе».
            seen["in_flight_during_stream"] = collector.in_flight
            yield "data: 1\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/v1/desk/{token}")
    def desk(token: str) -> dict:
        return {}

    @app.get("/api/v1/desk/{token}/widget/{key}")
    def desk_widget(token: str, key: str) -> dict:
        return {}

    @app.get("/api/v1/with-background")
    def with_background(background: BackgroundTasks) -> dict:
        def slow_tail() -> None:
            seen["in_flight_during_background"] = collector.in_flight
            seen["background_started_at"] = datetime.utcnow()
            time.sleep(0.3)

        background.add_task(slow_tail)
        return {}

    @app.get("/api/v1/background-boom")
    def background_boom(background: BackgroundTasks) -> dict:
        def fail() -> None:
            raise RuntimeError("сбой фоновой задачи")

        background.add_task(fail)
        return {}

    app.add_middleware(PerfMiddleware, collector=collector)
    return TestClient(app, raise_server_exceptions=False)


seen: dict = {}


def test_records_route_template_not_concrete_path():
    c = PerfCollector(enabled=True, slow_ms=10 ** 9)
    client = _app(c)
    assert client.get("/api/v1/items/42").status_code == 200
    assert client.get("/api/v1/items/43").status_code == 200

    aggs, slow = c.drain()
    assert slow == []
    [(key, agg)] = aggs.items()
    assert key[1:] == ("GET", "/api/v1/items/{item_id}")
    assert agg.count == 2
    assert c.in_flight == 0


def test_counts_db_queries_of_request():
    install_query_listeners()
    c = PerfCollector(enabled=True, slow_ms=10 ** 9)
    _app(c).get("/api/v1/items/1")
    [agg] = c.drain()[0].values()
    assert agg.db_count == 1


def test_unhandled_error_counts_as_5xx():
    c = PerfCollector(enabled=True, slow_ms=10 ** 9)
    assert _app(c).get("/api/v1/boom").status_code == 500
    [agg] = c.drain()[0].values()
    assert agg.errors_5xx == 1


def test_slow_request_keeps_details_without_secrets():
    install_query_listeners()
    c = PerfCollector(enabled=True, slow_ms=0)
    _app(c).get(
        "/api/v1/items/7?team=Альфа&token=abc&password=p&client_secret=s&api_key=k",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    _, slow = c.drain()
    [s] = slow
    assert s["route"] == "/api/v1/items/{item_id}"
    assert s["path"] == "/api/v1/items/7"
    assert s["method"] == "GET"
    assert s["status_code"] == 200
    assert s["query"] == "team=Альфа"
    assert s["db_count"] == 1
    assert s["top_queries"] and "SELECT 1" in s["top_queries"][0]["sql"]
    assert s["user_id"] is None  # подпись токена не сошлась
    assert "cpu_ms" in s and s["duration_ms"] >= 0


@pytest.mark.parametrize(
    "path", ["/api/v1/admin/perf/overview", "/health", "/api/v1/stream", "/api/v1/nope"],
)
def test_skipped_paths(path):
    c = PerfCollector(enabled=True, slow_ms=0)
    _app(c).get(path)
    assert c.drain() == ({}, [])
    assert c.in_flight == 0


def test_disabled_collector_records_nothing():
    c = PerfCollector(enabled=False, slow_ms=0)
    _app(c).get("/api/v1/items/1")
    assert c.drain() == ({}, [])


def test_sanitize_query_drops_secret_like_params():
    raw = "a=1&access_token=x&Password=y&my_secret=z&session_id=q&b=%D0%AF".encode()
    assert sanitize_query(raw) == "a=1&b=Я"
    assert sanitize_query(b"") == ""
    assert sanitize_query(b"a=x%00y") == "a=xy"  # NUL ломает запись на PostgreSQL


@pytest.mark.parametrize("method", ["UNSUBSCRIBE", "POST", "HEAD"])
def test_method_outside_route_is_not_recorded(method):
    """405 на частичном совпадении: метод — произвольная строка, в таблицу не идёт."""
    c = PerfCollector(enabled=True, slow_ms=0)
    resp = _app(c).request(method, "/api/v1/items/1")
    assert resp.status_code == 405
    assert c.drain() == ({}, [])
    assert c.in_flight == 0


def test_nul_in_path_is_stripped():
    c = PerfCollector(enabled=True, slow_ms=0)
    _app(c).get("/api/v1/items/a%00b")
    [s] = c.drain()[1]
    assert s["path"] == "/api/v1/items/ab"


def test_secret_path_params_are_masked():
    c = PerfCollector(enabled=True, slow_ms=0)
    client = _app(c)
    client.get("/api/v1/desk/s3cr3t-desk-token")
    client.get("/api/v1/desk/s3cr3t-desk-token/widget/hours")
    paths = sorted(s["path"] for s in c.drain()[1])
    assert paths == ["/api/v1/desk/***", "/api/v1/desk/***/widget/hours"]


def test_event_stream_leaves_in_flight_at_headers():
    seen.clear()
    c = PerfCollector(enabled=True, slow_ms=0)
    _app(c).get("/api/v1/stream")
    assert seen["in_flight_during_stream"] == 0
    assert c.in_flight == 0  # и без двойного вычитания


def test_background_task_not_counted_in_time_or_in_flight():
    seen.clear()
    c = PerfCollector(enabled=True, slow_ms=0)
    _app(c).get("/api/v1/with-background")
    [s] = c.drain()[1]
    assert seen["in_flight_during_background"] == 0
    assert s["duration_ms"] < 300  # фоновая задача спит 0,3 с
    assert s["at"] <= seen["background_started_at"]
    assert c.in_flight == 0


def test_failed_background_task_keeps_sent_status():
    c = PerfCollector(enabled=True, slow_ms=10 ** 9)
    _app(c).get("/api/v1/background-boom")
    [agg] = c.drain()[0].values()
    assert agg.errors_5xx == 0


def test_real_app_measures_api_routes(testclient_db_session):
    """Слой подключён к приложению; включается вместе с циклом записи (lifespan)."""
    from app.config import get_settings
    from app.database import get_db
    from app.main import app as real_app, perf_collector

    assert get_settings().perf_enabled is False  # в тестах цикл записи не стартует
    real_app.dependency_overrides[get_db] = lambda: testclient_db_session
    perf_collector.drain()
    perf_collector.enabled = True
    try:
        TestClient(real_app).get("/api/v1/admin/errors")
        aggs, _ = perf_collector.drain()
    finally:
        perf_collector.enabled = False
        real_app.dependency_overrides.pop(get_db, None)
    assert [k[1:] for k in aggs] == [("GET", "/api/v1/admin/errors")]
