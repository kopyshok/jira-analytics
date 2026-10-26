"""Ожидание блокировки в базе не вешает весь сервис (инцидент 23.10.2026).

Боевой сервис встал: подтверждение категории задачи ждало строку, которую
держала незакреплённая порция синхронизации, и ждало прямо на общем цикле
обработки. Синку, чтобы закрепить порцию, нужен тот же цикл — круг замкнулся,
не отвечала даже проверка здоровья.

Только Postgres: SQLite блокирует файл целиком и ждёт по-своему. Сервер —
настоящий uvicorn в отдельном потоке, один цикл на все запросы, как на проде.
"""

import asyncio
import os
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import models as _all_models  # noqa: F401 — все модели в metadata
from app.database import Base, get_db, postgres_connect_args
from app.main import app
from app.models.issue import Issue
from app.models.project import Project

URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")

pytestmark = pytest.mark.skipif(
    make_url(URL).get_backend_name() != "postgresql",
    reason="блокировки строк — только на Postgres (TEST_DATABASE_URL)",
)

LOCK_TIMEOUT_S = 2
ISSUE_ID = "lock-issue-1"


@pytest.fixture
def pg():
    """Движок с теми же пределами ожидания, что у приложения (короче — ради скорости теста)."""
    engine = create_engine(URL, connect_args=postgres_connect_args(lock_timeout_s=LOCK_TIMEOUT_S))
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with Session() as s:
        s.add(Project(id="lock-p1", jira_project_id="JL1", key="LCK", name="Lock"))
        s.add(Issue(
            id=ISSUE_ID, jira_issue_id="9001", key="LCK-1", summary="Задача",
            issue_type="Task", status="To Do", project_id="lock-p1",
            category_verified=False,
        ))
        s.commit()

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_db, None)
        with engine.begin() as conn:
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(table.delete())
        engine.dispose()


@pytest.fixture
def server(pg):
    """Настоящий uvicorn без lifespan: один цикл обработки на все запросы."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="warning"))
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_until_complete, args=(srv.serve(),), daemon=True)
    thread.start()
    while not srv.started:
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}", loop
    finally:
        srv.should_exit = True
        thread.join(timeout=10)


def _post_verify(base: str, out: dict) -> None:
    t0 = time.monotonic()
    try:
        r = httpx.post(
            f"{base}/api/v1/issues/{ISSUE_ID}/verify",
            json={"cascade": False, "require_child_verification": False},
            timeout=30,
        )
        out["status"], out["body"] = r.status_code, r.json()
    except Exception as exc:  # noqa: BLE001 — тест разбирает любой исход
        out["error"] = repr(exc)
    out["elapsed"] = time.monotonic() - t0


def _terminate_app_lock_waiters(engine) -> None:
    """Аварийно разорвать ожидание, чтобы упавший тест не повесил прогон."""
    with engine.connect() as conn:
        conn.execute(text(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid() "
            "AND (wait_event_type = 'Lock' OR state LIKE 'idle in transaction%')"
        ))
        conn.commit()


def _open_transactions(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE datname = current_database() AND state LIKE 'idle in transaction%'"
        )).scalar_one()


def test_lock_wait_times_out_and_app_stays_alive(pg, server):
    """Чужая незакреплённая правка задачи: подтверждение получает понятный отказ
    через предел ожидания, а сервис всё это время отвечает. Повтор проходит."""
    base, _ = server
    holder = pg.connect()
    tx = holder.begin()
    holder.execute(text("UPDATE issues SET synced_at = now() WHERE id = :id"), {"id": ISSUE_ID})

    verify: dict = {}
    t = threading.Thread(target=_post_verify, args=(base, verify), daemon=True)
    try:
        t.start()
        time.sleep(0.5)  # подтверждение дошло до ожидания строки

        t0 = time.monotonic()
        try:
            health = httpx.get(f"{base}/health", timeout=1.5)
        except httpx.TimeoutException:
            health = None
        assert health is not None and health.status_code == 200, (
            f"проверка здоровья не ответила за {time.monotonic() - t0:.1f} с — цикл обработки стоит"
        )

        t.join(timeout=LOCK_TIMEOUT_S + 5)
        assert verify.get("status") == 409, verify
        assert "повторите" in verify["body"]["detail"].lower()
        assert verify["elapsed"] < LOCK_TIMEOUT_S + 3
    finally:
        tx.rollback()
        holder.close()
        t.join(timeout=10)

    assert _open_transactions(pg) == 0
    retry: dict = {}
    _post_verify(base, retry)
    assert retry.get("status") == 200, retry
    with pg.connect() as conn:
        assert conn.execute(
            text("SELECT category_verified FROM issues WHERE id = :id"), {"id": ISSUE_ID},
        ).scalar_one() is True


def test_sync_on_loop_holding_batch_does_not_deadlock(pg, server):
    """Ровно инцидент: синк на том же цикле держит незакреплённую порцию и ушёл
    ждать Jira. Подтверждение не должно останавливать цикл — синк закрепляет
    порцию, подтверждение проходит."""
    base, loop = server
    Session = sessionmaker(bind=pg)

    async def sync_batch() -> None:
        with Session() as db:
            db.execute(text("UPDATE issues SET synced_at = now() WHERE id = :id"), {"id": ISSUE_ID})
            await asyncio.sleep(1.0)  # синк ждёт следующую страницу Jira
            db.commit()

    fut = asyncio.run_coroutine_threadsafe(sync_batch(), loop)
    time.sleep(0.3)  # порция открыта

    verify: dict = {}
    t = threading.Thread(target=_post_verify, args=(base, verify), daemon=True)
    try:
        t.start()
        t.join(timeout=LOCK_TIMEOUT_S + 5)
        assert verify.get("status") == 200, f"подтверждение не прошло: {verify or 'висит'}"
        fut.result(timeout=5)
    finally:
        if t.is_alive() or not fut.done():
            _terminate_app_lock_waiters(pg)
        t.join(timeout=10)


def test_sync_session_waits_for_locks_briefly(pg):
    """Синк работает в цикле обработки: чужую блокировку он ждёт коротко,
    иначе на время ожидания стоит весь сервис."""
    from unittest.mock import MagicMock

    from app.services.sync_service import SYNC_LOCK_TIMEOUT, SyncService

    with sessionmaker(bind=pg)() as db:
        SyncService(db, MagicMock())
        assert db.execute(text("SHOW lock_timeout")).scalar_one() == SYNC_LOCK_TIMEOUT
        db.commit()
        assert db.execute(text("SHOW lock_timeout")).scalar_one() == SYNC_LOCK_TIMEOUT
    with pg.connect() as conn:  # пул: соединение вернулось с обычным пределом приложения
        assert conn.execute(text("SHOW lock_timeout")).scalar_one() == f"{LOCK_TIMEOUT_S}s"
