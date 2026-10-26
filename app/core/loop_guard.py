"""Запросы к базе — не в цикле обработки запросов.

Весь сервис — один цикл обработки. Обращение к базе из асинхронного
обработчика выполняется прямо в нём: пока база отвечает или ждёт чужую
блокировку, не отвечает никто. 23.10.2026 так встал прод — подтверждение
категории ждало строку, которую держала порция синка, а синку для фиксации
нужен тот же цикл.

Правило: обработчик с базой — обычная функция (FastAPI выполняет её в
рабочем потоке); асинхронной остаётся только работа с сетью, а база из неё —
через рабочий поток. Здесь — проверка правила: в тестах нарушение роняет
запрос, на проде пишется предупреждение (раз на обработчик).

Синк — исключение: он работает в цикле и помечен ``db_on_loop_allowed``.
ponytail: синк в цикле — известный потолок. Покажет сторож долгие остановки
цикла из-за синка — переносить синк в свой поток.
"""

import asyncio
import logging
from contextvars import ContextVar
from typing import Any, Callable, Optional, TypeVar

import anyio
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Запрос и цикл, который его обслуживает.
_request_scope: ContextVar[Optional[tuple[Scope, asyncio.AbstractEventLoop]]] = ContextVar(
    "request_scope", default=None,
)
_on_loop_allowed: ContextVar[bool] = ContextVar("db_on_loop_allowed", default=False)
_reported: set[str] = set()


async def run_blocking(fn: Callable[..., T], *args: Any) -> T:
    """Тяжёлую синхронную работу синка — в рабочий поток, цикл свободен.

    Отмена дожидается конца работы: поток не прервать, а сессия у него общая
    с вызывающим — вернуть управление раньше значило бы отдать одну сессию
    двум потокам сразу.
    """
    work = asyncio.ensure_future(asyncio.to_thread(fn, *args))
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        # Повторная отмена не отпускает раньше потока.
        while not work.done():
            try:
                await asyncio.wait([work])
            except asyncio.CancelledError:
                pass
        work.exception()  # ошибка потока после отмены не нужна — забрать, чтобы asyncio не шумел
        raise


async def cancel_and_wait(task: asyncio.Task) -> None:
    """Отменить задачу и дождаться её конца, даже если отменяют нас самих.

    Поток событий при обрыве связи anyio отменяет заново на каждом ожидании,
    а задача могла держать общую сессию в рабочем потоке (``run_blocking``):
    не дождавшись, вызывающий тронул бы сессию одновременно с потоком.
    """
    task.cancel()
    with anyio.CancelScope(shield=True):
        await asyncio.wait([task])
    if not task.cancelled():
        task.exception()  # забрать, чтобы asyncio не писал «exception was never retrieved»


async def db_on_loop_allowed() -> None:
    """Зависимость маршрута синка: ему разрешено ходить в базу из цикла.

    Асинхронная — выполняется в задаче самого запроса, поэтому отметка
    действует до конца запроса, включая поток событий и порождённые задачи.
    """
    _on_loop_allowed.set(True)


class RequestScopeMiddleware:
    """Отмечает, что код выполняется ради HTTP-запроса (для проверки выше)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = _request_scope.set((scope, asyncio.get_running_loop()))
        try:
            await self.app(scope, receive, send)
        finally:
            _request_scope.reset(token)


@event.listens_for(Engine, "before_cursor_execute")
def _forbid_db_on_event_loop(conn, cursor, statement, parameters, context, executemany) -> None:
    request = _request_scope.get()
    if request is None or _on_loop_allowed.get():
        return
    scope, request_loop = request
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        return  # рабочий поток — так и надо
    if running is not request_loop:
        return  # свой цикл в рабочем потоке (asyncio.run из to_thread) — общий не держит
    route = scope.get("route")
    where = f"{scope.get('method')} {getattr(route, 'path', None) or scope.get('path')}"
    if get_settings().db_loop_guard_strict:
        raise RuntimeError(f"Запрос к базе в цикле обработки запросов: {where}")
    if where not in _reported:
        _reported.add(where)
        logger.warning("Запрос к базе в цикле обработки запросов (может подвесить сервис): %s", where)
