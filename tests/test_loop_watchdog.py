"""Сторож цикла: снимок потоков при остановке цикла, перезапуск — при долгой."""

import asyncio
import logging
import threading
import time

from app.core import loop_watchdog


def _loop_in_thread() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def test_stalled_loop_is_reported_then_restarted(caplog):
    loop = _loop_in_thread()
    exited = threading.Event()
    codes: list[int] = []

    def fake_exit(code: int) -> None:
        codes.append(code)
        exited.set()

    caplog.set_level(logging.WARNING, logger="app.core.loop_watchdog")
    stop = loop_watchdog.start(loop, stall_after=0.3, restart_after=0.8, check_every=0.05, exit_process=fake_exit)
    try:
        loop.call_soon_threadsafe(time.sleep, 1.5)  # цикл занят и не отмечается
        assert exited.wait(timeout=5)
        assert codes == [loop_watchdog.RESTART_EXIT_CODE]
        text = caplog.text
        assert "не отвечает" in text and "Снимок потоков" in text
        assert "run_forever" in text  # в снимке — поток самого цикла
    finally:
        stop.set()
        loop.call_soon_threadsafe(loop.stop)


def test_healthy_loop_is_left_alone(caplog):
    loop = _loop_in_thread()
    codes: list[int] = []
    caplog.set_level(logging.WARNING, logger="app.core.loop_watchdog")
    stop = loop_watchdog.start(loop, stall_after=0.3, restart_after=0.6, check_every=0.05, exit_process=codes.append)
    try:
        time.sleep(1.0)
        assert codes == []
        assert "не отвечает" not in caplog.text
    finally:
        stop.set()
        loop.call_soon_threadsafe(loop.stop)
