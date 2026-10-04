"""Промежуточный слой замеров: что и как попадает в сборщик."""
import pytest
from fastapi import FastAPI
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
        return StreamingResponse(iter(["data: 1\n\n"]), media_type="text/event-stream")

    app.add_middleware(PerfMiddleware, collector=collector)
    return TestClient(app, raise_server_exceptions=False)


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
