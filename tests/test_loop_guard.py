"""База — не в цикле обработки запросов: проверка правила и вынос работы в поток."""

import asyncio
import threading
import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.core.loop_guard import RequestScopeMiddleware, db_on_loop_allowed, run_blocking

engine = create_engine("sqlite://")
app = FastAPI()
app.add_middleware(RequestScopeMiddleware)


def _query() -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1")).scalar_one()


@app.get("/on-loop")
async def on_loop():
    return _query()


@app.get("/in-thread")
def in_thread():
    return _query()


@app.get("/sync-run", dependencies=[Depends(db_on_loop_allowed)])
async def sync_run():
    return _query()


def test_db_on_event_loop_inside_request_is_an_error():
    with pytest.raises(RuntimeError, match="Запрос к базе в цикле обработки запросов: GET /on-loop"):
        TestClient(app).get("/on-loop")


def test_db_in_worker_thread_and_marked_sync_route_are_fine():
    client = TestClient(app)
    assert client.get("/in-thread").json() == 1
    assert client.get("/sync-run").json() == 1


async def test_run_blocking_cancel_waits_for_thread():
    """Отмена не возвращает управление, пока поток держит общую сессию."""
    finished = threading.Event()

    def work() -> None:
        time.sleep(0.3)
        finished.set()

    task = asyncio.create_task(run_blocking(work))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()
