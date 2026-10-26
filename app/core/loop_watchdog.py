"""Сторож цикла обработки запросов.

Весь сервис — один цикл. Если его что-то держит (ожидание базы, тяжёлый
расчёт прямо в цикле), не отвечает никто, даже проверка здоровья, а Docker
перезапускает только упавший процесс, не зависший. Сторож из своего потока
раз в несколько секунд просит цикл отметиться:

- цикл молчит дольше ``stall_after`` — в журнал снимок всех потоков (что
  держит цикл); сервис не трогается;
- молчит дольше ``restart_after`` — ещё снимок и выход процесса: Docker
  поднимет сервис заново, оборванный синк закроется при старте.

Снимок по требованию, без перезапуска: ``docker compose kill -s USR1 backend``.
"""

import asyncio
import faulthandler
import logging
import os
import signal
import sys
import threading
import time
import traceback
from typing import Callable

logger = logging.getLogger(__name__)

#: Код выхода при перезапуске сторожем — отличим в журнале Docker от падения.
RESTART_EXIT_CODE = 70


def thread_dump() -> str:
    """Где сейчас стоит каждый поток процесса."""
    names = {t.ident: t.name for t in threading.enumerate()}
    parts = []
    for ident, frame in sys._current_frames().items():
        parts.append(f"--- поток {names.get(ident, ident)} ---\n" + "".join(traceback.format_stack(frame)))
    return "\n".join(parts)


def start(
    loop: asyncio.AbstractEventLoop,
    *,
    stall_after: float,
    restart_after: float,
    check_every: float = 5.0,
    exit_process: Callable[[int], None] = os._exit,
) -> threading.Event:
    """Запустить сторожа; вернуть флаг остановки. ``restart_after=0`` — не перезапускать."""
    if sys.platform != "win32":  # на Windows нет SIGUSR1
        faulthandler.register(signal.SIGUSR1, file=sys.stderr, all_threads=True)

    last_beat = time.monotonic()
    stop = threading.Event()

    def beat() -> None:
        nonlocal last_beat
        last_beat = time.monotonic()

    def watch() -> None:
        reported = False
        while not stop.wait(check_every):
            try:
                loop.call_soon_threadsafe(beat)
            except RuntimeError:
                return  # цикл закрыт — сервис останавливается
            silent = time.monotonic() - last_beat
            if silent < stall_after:
                if reported:
                    logger.warning("Цикл обработки запросов снова отвечает")
                reported = False
                continue
            if not reported:
                reported = True
                logger.error("Цикл обработки запросов не отвечает %.0f с. Снимок потоков:\n%s", silent, thread_dump())
            if restart_after and silent >= restart_after:
                logger.critical("Цикл не отвечает %.0f с — сервис перезапускается. Снимок потоков:\n%s", silent, thread_dump())
                exit_process(RESTART_EXIT_CODE)
                return

    threading.Thread(target=watch, name="loop-watchdog", daemon=True).start()
    return stop
