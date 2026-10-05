"""Промежуточный слой замеров быстродействия.

Чистый ASGI, а не `BaseHTTPMiddleware`: не буферизует ответ и не ломает потоки.
Шаблон пути берётся из `scope["route"]`, который FastAPI кладёт при
маршрутизации, — в агрегат идёт `/api/v1/backlog/{item_id}`, а не адрес.

Не замеряются: всё вне `/api/`, собственные эндпоинты раздела (иначе шум),
потоки событий (`text/event-stream` живут минутами) и несматченные пути
(иначе любой может засорить таблицу произвольными адресами).

Время — до последнего куска тела: фоновые задачи ответа клиент не ждёт.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from time import perf_counter, process_time
from typing import Any, Optional
from urllib.parse import parse_qsl

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.perf import PerfCollector, RequestStats, current_stats

logger = logging.getLogger(__name__)

API_PREFIX = "/api/"
OWN_PREFIX = "/api/v1/admin/perf"
QUERY_MAX_CHARS = 1000

_SECRET_PARAM = re.compile(
    r"token|password|passwd|pwd|secret|api[_-]?key|auth|credential|session|cookie", re.I,
)


_PATH_PARAM = re.compile(r"\{(\w+)\}")


def _no_nul(s: str) -> str:
    # PostgreSQL не принимает символ NUL в тексте — вся пачка сброса упала бы.
    return s.replace("\x00", "")


def sanitize_query(raw: bytes) -> str:
    """Параметры запроса в читаемом виде, без похожих на секреты."""
    if not raw:
        return ""
    pairs = parse_qsl(raw.decode("latin-1"), keep_blank_values=True)
    text = "&".join(f"{k}={v}" for k, v in pairs if not _SECRET_PARAM.search(k))
    return _no_nul(text)[:QUERY_MAX_CHARS]


def _route_template(scope: Scope, route: Any) -> str:
    """Полный шаблон пути маршрута: `/api/v1/planning/scenarios/{scenario_id}`.

    Старый FastAPI копировал маршруты подключённого роутера с полным путём; новый
    (0.14x) не копирует — у маршрута путь относительно роутера (у `@router.get("")`
    пустой), префикс есть только в адресе запроса. Префикс берём из адреса: отрезаем
    от него относительный путь с подставленными параметрами.
    """
    fmt: str = getattr(route, "path_format", None) or getattr(route, "path", None) or ""
    params = scope.get("path_params") or {}
    path: str = scope.get("path", "")
    rendered = _PATH_PARAM.sub(lambda m: str(params.get(m.group(1), m.group(0))), fmt)
    if path.endswith(rendered):
        return path[: len(path) - len(rendered)] + fmt
    return fmt


def _safe_path(scope: Scope, route: Any) -> str:
    """Адрес запроса; параметры пути с секретными именами (`/desk/{token}`) — звёздочками."""
    params = scope.get("path_params") or {}
    path = scope.get("path", "")
    if any(_SECRET_PARAM.search(name) for name in params):
        fmt = _route_template(scope, route)
        path = _PATH_PARAM.sub(
            lambda m: "***" if _SECRET_PARAM.search(m.group(1))
            else str(params.get(m.group(1), m.group(0))),
            fmt,
        )
    return _no_nul(path)


def _user_id(scope: Scope) -> Optional[str]:
    from app.core.error_log import _user_id_from

    return _user_id_from(Request(scope))


class PerfMiddleware:
    def __init__(self, app: ASGIApp, collector: PerfCollector) -> None:
        self.app = app
        self.collector = collector

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "") if scope["type"] == "http" else ""
        if (
            not self.collector.enabled
            or not path.startswith(API_PREFIX)
            or path.startswith(OWN_PREFIX)
        ):
            await self.app(scope, receive, send)
            return

        collector = self.collector
        stats = RequestStats()
        token = current_stats.set(stats)
        collector.request_started()
        t0, cpu0 = perf_counter(), process_time()
        state: dict[str, Any] = {
            "status": 500, "end": None, "cpu_end": None, "wall_end": None,
            "stream": False, "counted_out": False,
        }

        def leave_in_flight() -> None:
            # Ровно один раз: и при потоке событий, и при конце ответа, и в finally.
            if not state["counted_out"]:
                state["counted_out"] = True
                collector.request_finished()

        def mark_end() -> None:
            # Конец ответа — последний кусок тела; фоновые задачи после него не считаются.
            if state["end"] is None:
                state["end"], state["cpu_end"] = perf_counter(), process_time()
                state["wall_end"] = datetime.utcnow()
                stats.closed = True
                leave_in_flight()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                for k, v in message.get("headers") or []:
                    if k.lower() == b"content-type" and v.startswith(b"text/event-stream"):
                        # Поток событий открыт часами (вкладка на /events) — не «запрос в работе».
                        state["stream"] = True
                        leave_in_flight()
            elif message["type"] == "http.response.body" and not message.get("more_body"):
                mark_end()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Ответ уже ушёл целиком (упала фоновая задача) — его код не меняем.
            if state["end"] is None:
                state["status"] = 500
            raise
        finally:
            current_stats.reset(token)
            mark_end()
            if not state["stream"]:
                try:
                    self._record(scope, state, t0, cpu0, stats)
                except Exception:  # замер не должен ронять запрос
                    logger.debug("perf: не удалось записать замер", exc_info=True)

    def _record(
        self, scope: Scope, state: dict[str, Any], t0: float, cpu0: float, stats: RequestStats,
    ) -> None:
        route = scope.get("route")
        template = _route_template(scope, route) if route is not None else None
        # Метод не из маршрута (405 на частичном совпадении, любые «UNSUBSCRIBE») —
        # не наш запрос, и произвольная строка не должна попасть в таблицу.
        if not template or scope["method"] not in (getattr(route, "methods", None) or ()):
            return
        duration_ms = (state["end"] - t0) * 1000
        now = state["wall_end"]
        slow = None
        if duration_ms >= self.collector.slow_ms:
            slow = {
                "at": now,
                "method": scope["method"],
                "route": template,
                "path": _safe_path(scope, route)[:500],
                "query": sanitize_query(scope.get("query_string", b"")),
                "status_code": state["status"],
                "duration_ms": duration_ms,
                "db_count": stats.db_count,
                "db_ms": stats.db_ms,
                "cpu_ms": (state["cpu_end"] - cpu0) * 1000,
                "user_id": _user_id(scope),
                "top_queries": stats.top_queries(),
            }
        self.collector.record(
            minute=now.replace(second=0, microsecond=0),
            method=scope["method"],
            route=template,
            duration_ms=duration_ms,
            status=state["status"],
            db_count=stats.db_count,
            db_ms=stats.db_ms,
            slow=slow,
        )
