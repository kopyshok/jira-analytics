"""Фоновые операции переезда: пробный прогон, применение, полная синхронизация после.

Каждая операция идёт в своём потоке со своим циклом событий и своей сессией
базы (как выгрузка базы): долгие чтения новой Jira и запись сотен тысяч строк
не занимают цикл, который обслуживает страницы сервиса. Ход операции — в
памяти процесса (сервис работает одним процессом); отчёт, итог применения и
запуск синхронизации — в базе.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

import anyio.from_thread
from sqlalchemy.orm import Session

from app.connectors.jira_client import JiraClient, JiraClientError
from app.database import SessionLocal
from app.models import SyncRun
from app.models.jira_migration import JiraMigrationReport
from app.repositories.sync_run import SyncRunRepository
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.jira_migration import store
from app.services.jira_migration.apply import ApplyRefused, apply_migration
from app.services.jira_migration.dry_run import DryRunAborted, build_report
from app.services.jira_migration.hours import history_start, post_check
from app.services.jira_migration.resolution import BLOCK_JOB
from app.services.mapping_service import MappingService
from app.services.production_calendar_service import ProductionCalendarService
from app.services.sync_lock import SyncLock, keep_lock, lock_keeper
from app.services.sync_pipeline import (
    PipelineOrchestrator,
    WorklogsFullStage,
    build_pipeline,
)
from app.services.sync_service import SyncService

logger = logging.getLogger(__name__)

KIND_DRY_RUN = "dry_run"
KIND_APPLY = "apply"
# Полная синхронизация после применения (сразу за ним или повтор со страницы).
KIND_FULL_SYNC = "full_sync"
JOB_IDLE = "idle"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"
STEP_APPLY = "Перепривязка данных к новой Jira"
STEP_FULL_SYNC = "Полная синхронизация с новой Jira"
DEFAULT_WORKLOG_DAYS = 90

RUN_INTERRUPTED = "Пробный прогон прерван (сервис перезапускался) — запустите его заново"
SYNC_INTERRUPTED = "Полная синхронизация прервана (сервис перезапускался) — запустите её заново"
JIRA_UNAVAILABLE = "Новая Jira недоступна — проверьте адрес и токен в настройках подключения"
DRY_RUN_FAILED = "Пробный прогон не удался из-за внутренней ошибки сервиса — подробности в журнале сервера"
APPLY_FAILED = "Применение не удалось, база не изменилась — подробности в журнале сервера"
FULL_SYNC_NOT_APPLIED = "Полная синхронизация доступна после применения переезда"
SYNC_BUSY = "Идёт другая синхронизация — запустите полную синхронизацию после её окончания"
FULL_SYNC_FAILED = (
    "Полная синхронизация после переезда не завершилась — подробности в истории синхронизаций, "
    "запустите её заново"
)
LOCK_LOST = (
    "Синхронизацию перехватил другой запуск — полная синхронизация после переезда остановлена, "
    "запустите её заново"
)
# Текст исключения из синка — только в журнал сервера; в историю запусков и на страницу — этот.
FULL_SYNC_ERROR = "Полная синхронизация прервалась с ошибкой — подробности в журнале сервера"
_KNOWN_RUN_ERRORS = frozenset({LOCK_LOST, SYNC_INTERRUPTED, FULL_SYNC_ERROR})

SessionFactory = Callable[[], Session]
JiraFactory = Callable[[Session], Any]


@dataclass
class MigrationJob:
    kind: Optional[str] = None
    state: str = JOB_IDLE
    step: Optional[str] = None
    counters: dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ponytail: состояние в памяти — сервис работает одним процессом uvicorn.
# Если появятся воркеры, переносить в базу.
_job = MigrationJob()
_lock = threading.Lock()


def current_job() -> MigrationJob:
    return _job


def is_running() -> bool:
    return _job.state == JOB_RUNNING


def report_in_progress(row: Optional[JiraMigrationReport], job: Optional[MigrationJob] = None) -> bool:
    """Отчёт строится прямо сейчас: «идёт», и пробный прогон идёт в этом процессе.

    Сервис работает одним процессом (``scripts/entrypoint.sh``): отчёт «идёт»
    без прогона здесь — прогон оборван перезапуском сервиса.
    """
    job = job if job is not None else _job
    return (
        row is not None
        and row.status == store.STATUS_RUNNING
        and job.state == JOB_RUNNING
        and job.kind == KIND_DRY_RUN
    )


def claim(db: Session, kind: str, *, now: Optional[datetime] = None) -> MigrationJob:
    """Занять слот фоновой операции. Уже идёт другая — ``RuntimeError``.

    Отчёт «идёт», а операции в этом процессе нет — прогон оборван
    перезапуском сервиса: отчёт сразу помечается неудачным.
    """
    global _job
    now = now or datetime.utcnow()
    with _lock:
        if _job.state == JOB_RUNNING:
            raise RuntimeError(BLOCK_JOB)
        row = store.latest_report(db)
        if row is not None and row.status == store.STATUS_RUNNING:
            store.fail_report(db, row.id, RUN_INTERRUPTED, now)
        _job = MigrationJob(kind=kind, state=JOB_RUNNING, started_at=now)
        return _job


def _progress(job: MigrationJob) -> Callable[..., None]:
    def update(step: str, counters: Optional[dict] = None) -> None:
        job.step = step
        if counters:
            job.counters.update(counters)
    return update


def _finish(job: MigrationJob, error: Optional[str] = None) -> None:
    # Состояние — последним: кто увидел «ошибка», увидит и её текст.
    job.error = error
    job.step = None
    job.finished_at = datetime.utcnow()
    job.state = JOB_ERROR if error else JOB_DONE


def _hand_over(job: MigrationJob, kind: str) -> MigrationJob:
    """Завершить операцию и сразу занять слот следующей — без промежутка «ничего не идёт»."""
    global _job
    with _lock:
        _finish(job)
        _job = MigrationJob(kind=kind, state=JOB_RUNNING, started_at=datetime.utcnow())
        return _job


def worklogs_history_start(report: dict) -> date:
    """С какой даты списаний сервис держит историю после переезда.

    Самая ранняя дата в базе до переезда, но не раньше ``HISTORY_START``:
    старую историю из новой Jira не загружаем (решение 16.10.2026).
    """
    raw = report.get("db_worklogs_min_date")
    earliest = date.fromisoformat(raw) if raw else date.today() - timedelta(days=DEFAULT_WORKLOG_DAYS)
    return history_start(earliest)


def worklogs_since(report: dict) -> date:
    """С какой даты изменений перечитать ворклоги: начало истории, днём раньше."""
    return worklogs_history_start(report) - timedelta(days=1)


# --- Отдельный поток ------------------------------------------------------------

class _ServiceLoopBus(EventBroadcaster):
    """События синхронизации из потока операции — подписчикам в цикле сервиса.

    Очереди подписчиков (открытые страницы) принадлежат циклу сервиса, класть
    в них из чужого потока нельзя — публикация передаётся в этот цикл.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        super().__init__()
        self._loop = loop
        self._target = get_event_bus()

    async def publish(self, event: dict[str, Any]) -> None:
        delivery = self._target.publish(event)
        try:
            asyncio.run_coroutine_threadsafe(delivery, self._loop)
        except RuntimeError:  # цикл сервиса закрыт — сервис останавливается
            delivery.close()


def _service_bus() -> EventBroadcaster:
    """Шина для операции в отдельном потоке; вызывать из обработчика запроса.

    Асинхронный обработчик идёт в цикле сервиса, обычный — в рабочем потоке,
    откуда цикл сервиса достаётся через anyio. Ни то ни другое — шина без
    подписчиков: события синхронизации никуда не уходят.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = anyio.from_thread.run_sync(asyncio.get_running_loop)
        except RuntimeError:
            return EventBroadcaster()
    return _ServiceLoopBus(loop)


def _start(name: str, operation: Callable[[], Coroutine[Any, Any, None]]) -> threading.Thread:
    """Запустить операцию в своём потоке со своим циклом событий."""

    def target() -> None:
        try:
            asyncio.run(operation())
        except Exception:  # noqa: BLE001 — поток не должен умереть молча
            logger.exception("Фоновая операция переезда «%s» упала", name)

    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()
    return thread


def start_dry_run(job: MigrationJob) -> threading.Thread:
    """Пробный прогон в отдельном потоке (слот занят :func:`claim`)."""
    return _start("jira-migration-dry-run", lambda: run_dry_run(job))


def start_apply(job: MigrationJob, *, backup_confirmed: bool) -> threading.Thread:
    """Применение и полная синхронизация после него — в отдельном потоке."""
    bus = _service_bus()
    return _start(
        "jira-migration-apply", lambda: run_apply(job, backup_confirmed=backup_confirmed, bus=bus),
    )


def start_full_sync_restart(job: MigrationJob) -> threading.Thread:
    """Повтор полной синхронизации после применения — в отдельном потоке.

    Слот занимает :func:`claim` с ``KIND_FULL_SYNC``: повторное нажатие получит отказ.
    """
    bus = _service_bus()
    return _start("jira-migration-full-sync", lambda: restart_full_sync(job, bus=bus))


# --- Операции ------------------------------------------------------------------

async def run_dry_run(
    job: MigrationJob,
    *,
    session_factory: SessionFactory = SessionLocal,
    jira_factory: JiraFactory = JiraClient.from_db,
) -> None:
    """Пробный прогон: отчёт в базу, ход — в ``job``.

    Сбой чтения новой Jira — причина по-русски из прогона; поломка в коде —
    общий текст, подробности (трассировка) — в журнал сервера.
    """
    db: Optional[Session] = None
    report_id: Optional[str] = None
    error: Optional[str] = None
    partial: Optional[dict] = None
    try:
        try:
            db = session_factory()
            report_id = store.start_report(db, datetime.utcnow())
            async with jira_factory(db) as jira:
                result = await build_report(db, jira, now=datetime.utcnow(), progress=_progress(job))
            store.finish_report(db, report_id, result.report, result.maps, datetime.utcnow())
        except DryRunAborted as exc:
            error, partial = str(exc), exc.report
        except JiraClientError:
            logger.warning("Пробный прогон переезда: новая Jira недоступна", exc_info=True)
            error = JIRA_UNAVAILABLE
        except Exception:  # noqa: BLE001 — отчёт и операция должны получить итог
            logger.exception("Пробный прогон переезда не удался")
            error = DRY_RUN_FAILED
        if error is not None and db is not None:
            db.rollback()
            store.fail_report(db, report_id, error, datetime.utcnow(), report=partial)
    finally:
        if db is not None:
            db.close()
        _finish(job, error)


async def run_apply(
    job: MigrationJob,
    *,
    backup_confirmed: bool,
    session_factory: SessionFactory = SessionLocal,
    jira_factory: JiraFactory = JiraClient.from_db,
    bus: Optional[EventBroadcaster] = None,
) -> None:
    """Применение; после фиксации — полная синхронизация всех ворклогов.

    Применение завершается сразу после фиксации (``job`` — «готово», страница
    обновляет признак «переезд завершён»), а слот тут же переходит к полной
    синхронизации (``KIND_FULL_SYNC``) до её окончания.
    """
    try:
        db = session_factory()
    except Exception:  # noqa: BLE001 — операция должна получить итог
        logger.exception("Применение переезда: нет подключения к базе")
        _finish(job, APPLY_FAILED)
        return
    try:
        job.step = STEP_APPLY
        try:
            summary = apply_migration(db, now=datetime.utcnow(), backup_confirmed=backup_confirmed)
        except ApplyRefused as exc:
            _finish(job, "Нельзя применить: " + "; ".join(exc.blockers))
            return
        except Exception:  # noqa: BLE001 — применение откатано, операция должна получить итог
            logger.exception("Применение переезда не удалось")
            _finish(job, APPLY_FAILED)
            return
        job.counters.update({key: value for key, value in summary.items() if isinstance(value, int)})
        await _full_sync_job(_hand_over(job, KIND_FULL_SYNC), db, jira_factory=jira_factory, bus=bus)
    finally:
        db.close()


def run_error_text(error: Optional[str]) -> Optional[str]:
    """Ошибка запуска полной синхронизации для истории и страницы.

    Свои тексты по-русски — как есть; сырой текст исключения — общий текст
    (подробности с трассировкой уже в журнале сервера).
    """
    if not error:
        return None
    return error if error in _KNOWN_RUN_ERRORS else FULL_SYNC_ERROR


def _sync_outcome(db: Session, run_id: Optional[str]) -> Optional[str]:
    """Текст ошибки для операции по итогу запуска синхронизации; ``None`` — успех."""
    if run_id is None:
        return SYNC_BUSY
    run = db.get(SyncRun, run_id)
    if run is None or run.status in ("ok", "partial"):
        return None
    if run.status == "skipped":
        return SYNC_BUSY
    return LOCK_LOST if run.error_text == LOCK_LOST else FULL_SYNC_FAILED


async def _full_sync_job(
    job: MigrationJob,
    db: Session,
    *,
    jira_factory: JiraFactory,
    bus: Optional[EventBroadcaster],
) -> None:
    """Полная синхронизация после применения как операция переезда: слот занят до конца."""
    error: Optional[str] = None
    try:
        job.step = STEP_FULL_SYNC
        row = store.latest_report(db)
        if row is None or row.applied_at is None:
            error = FULL_SYNC_NOT_APPLIED
        else:
            # Прежний запуск этого переезда сейчас не идёт: слот операции у нас.
            run_id = await run_full_sync(
                db, row.id, worklogs_since(store.report_data(row)),
                started_from=worklogs_history_start(store.report_data(row)), jira_factory=jira_factory, bus=bus,
                previous_run_id=row.sync_run_id,
            )
            error = _sync_outcome(db, run_id)
    except Exception:  # noqa: BLE001 — переезд применён; синхронизацию можно запустить со страницы
        logger.exception("Полная синхронизация после переезда не запустилась")
        error = FULL_SYNC_FAILED
    finally:
        _finish(job, error)


async def run_full_sync(
    db: Session,
    report_id: str,
    worklogs_since_date: date,
    *,
    started_from: Optional[date] = None,
    jira_factory: JiraFactory = JiraClient.from_db,
    bus: Optional[EventBroadcaster] = None,
    previous_run_id: Optional[str] = None,
) -> Optional[str]:
    """Полная синхронизация задач и всех ворклогов из новой Jira после применения.

    Обычный конвейер «полный», но ворклоги — с самой ранней даты списаний в
    базе до переезда, а не за 90 дней: применение удалило их все.
    ``started_from`` — ворклоги с более ранней датой списания не загружаются
    (фильтр по дате изменения их не отсекает: перенос мог её обновить). Запуск —
    как у синхронизации по расписанию: блокировка, запись в историю. Идёт
    другая синхронизация — не запускается (``None``). Синхронизация идёт
    часами, а блокировка через час считается зависшей — она продлевается
    перед каждой стадией и по ходу стадий синка; если её всё же забрал
    другой запуск, синхронизация останавливается (``LOCK_LOST`` в истории),
    а чужая блокировка не снимается.

    ``previous_run_id`` — прежний запуск этого переезда, который сейчас
    заведомо не идёт (оборван перезапуском сервиса): его блокировка не
    мешает, а сам он в истории закрывается как прерванный.
    """
    lock = SyncLock(db)
    holder = lock.current_run_id()
    if holder and holder != previous_run_id and not lock.is_stale():
        logger.warning("Полная синхронизация после переезда не запущена: идёт другая синхронизация")
        return None
    runs = SyncRunRepository(db)
    previous = runs.get(previous_run_id) if previous_run_id else None
    if previous is not None and previous.status == "running":
        runs.finalize(previous.id, status="failed", stages=previous.stages_json or [], error_text=SYNC_INTERRUPTED)
    run_id = runs.create(mode="full", trigger="manual").id
    if not lock.acquire(run_id, replacing=previous_run_id):
        runs.finalize(run_id, status="skipped", stages=[], error_text="lock contention")
        return None
    try:
        store.set_sync_run(db, report_id, run_id)
        async with jira_factory(db) as jira:
            sync_service = SyncService(db, jira, cancel_check=lock_keeper(lock, run_id, LOCK_LOST))
            stages = [
                WorklogsFullStage(sync_service, since=worklogs_since_date, started_from=started_from)
                if isinstance(stage, WorklogsFullStage) else stage
                for stage in build_pipeline(
                    mode="full",
                    services={
                        "sync": sync_service,
                        "calendar": ProductionCalendarService(db),
                        "mapping": MappingService(db),
                    },
                )
            ]
            orchestrator = PipelineOrchestrator(
                stages=stages, db=db, bus=bus or get_event_bus(),
                before_stage=lambda: keep_lock(lock, run_id, LOCK_LOST),
            )
            result = await orchestrator.run(mode="full", trigger="manual", run_id=run_id)
        # Сбой стадии конвейер уже записал в журнал с трассировкой.
        runs.finalize(
            run_id, status=result["status"], stages=result.get("stages", []),
            error_text=run_error_text(result.get("error")),
        )
    except Exception:  # noqa: BLE001 — запуск в истории должен получить итог
        logger.exception("Полная синхронизация после переезда упала")
        db.rollback()
        runs.finalize(run_id, status="failed", stages=[], error_text=FULL_SYNC_ERROR)
    finally:
        lock.release(run_id)
    return run_id


async def restart_full_sync(
    job: MigrationJob,
    *,
    session_factory: SessionFactory = SessionLocal,
    jira_factory: JiraFactory = JiraClient.from_db,
    bus: Optional[EventBroadcaster] = None,
) -> None:
    """Повтор полной синхронизации после применения (не стартовала или упала)."""
    try:
        db = session_factory()
    except Exception:  # noqa: BLE001 — операция должна получить итог
        logger.exception("Повтор полной синхронизации после переезда: нет подключения к базе")
        _finish(job, FULL_SYNC_FAILED)
        return
    try:
        await _full_sync_job(job, db, jira_factory=jira_factory, bus=bus)
    finally:
        db.close()


def post_check_latest(db: Session, *, now: datetime) -> dict:
    """Сверка после: часы базы сейчас против новой Jira из отчёта. Сохраняется в отчёт."""
    row = store.latest_report(db)
    if row is None or row.applied_at is None:
        raise ValueError("Сверка доступна после применения переезда")
    result = post_check(db, store.report_data(row), now)
    store.save_post_check(db, row.id, result)
    return result
