"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.api.router import api_router
from app.core import error_log, loop_watchdog
from app.core.loop_guard import RequestScopeMiddleware
from app.core.perf import PerfCollector, install_query_listeners
from app.core.perf_middleware import PerfMiddleware
from app.database import SessionLocal, engine
from app.services.kpi.conditions import ConditionError
from app.services.jira_migration.state import SyncBlockedError
from app.repositories.sync_schedule import SyncScheduleRepository
from app.services.scheduler import SchedulerService, close_interrupted_runs, scheduled_pipeline_runner
from app.jobs.aggregate_usage import aggregate_usage_job
from app.jobs.regenerate_summaries import regenerate_outdated_summaries_blocking
from app.services.token_renewal import renew_tokens_job
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

#: Замеры быстродействия. Включается в lifespan вместе с циклом записи — без
#: цикла сборщик копил бы замеры в памяти бесконечно.
perf_collector = PerfCollector(enabled=False, slow_ms=settings.perf_slow_ms)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("Debug mode: %s", settings.debug)
    logger.info("Database: %s", make_url(settings.database_url).render_as_string(hide_password=True))

    # Сторож цикла обработки запросов: снимок потоков при остановке цикла,
    # перезапуск — при долгой (Docker поднимает процесс заново).
    watchdog_stop = loop_watchdog.start(
        asyncio.get_running_loop(),
        stall_after=settings.loop_watchdog_stall_seconds,
        restart_after=settings.loop_watchdog_restart_seconds,
    )

    # --- Release notes seed from release_notes/*.json ---
    from app.services.release_note_seed import seed_with_retry

    seed_with_retry(SessionLocal)

    # --- Scheduler ---
    db = SessionLocal()
    try:
        # Запуски «Выполняется» от прошлого процесса уже не идут.
        close_interrupted_runs(db)
        schedules = SyncScheduleRepository(db).list_all()
    finally:
        db.close()

    sched_svc = SchedulerService(trigger_runner=scheduled_pipeline_runner)
    sched_svc.register_jobs(schedules)
    sched_svc.start()
    sched_svc.scheduler.add_job(
        regenerate_outdated_summaries_blocking,
        trigger=CronTrigger(hour=3, minute=0),
        id="regenerate_summaries",
        replace_existing=True,
        max_instances=1,
    )
    sched_svc.scheduler.add_job(
        aggregate_usage_job,
        trigger=CronTrigger(hour=3, minute=10),
        id="aggregate_usage",
        replace_existing=True,
        max_instances=1,
    )
    # Самопродление токенов Jira/Confluence: раз в час, первый раз — через минуту после старта.
    sched_svc.scheduler.add_job(
        renew_tokens_job,
        trigger=IntervalTrigger(hours=1),
        id="renew_tokens",
        replace_existing=True,
        max_instances=1,
        next_run_time=datetime.now() + timedelta(minutes=1),
    )
    app.state.scheduler = sched_svc

    # --- Разовое дозаполнение «автора задачи» (background, non-blocking) ---
    # Отрабатывает один раз на окружение при обновлении на версию с
    # исправленным чтением Автора из Jira; дальше сам себя пропускает.
    from app.jobs.backfill_issue_author import backfill_issue_author_once
    backfill_task = asyncio.create_task(backfill_issue_author_once())
    app.state.backfill_author_task = backfill_task

    # --- Быстродействие: замеры запросов и нагрузки сервера ---
    perf_task = None
    if settings.perf_enabled:
        from app.services.perf_writer import run_loop

        install_query_listeners()
        perf_collector.enabled = True
        perf_task = asyncio.create_task(run_loop(
            perf_collector,
            interval=settings.perf_flush_seconds,
            retention_days=settings.perf_retention_days,
            session_factory=SessionLocal,
            engine=engine,
        ))

    yield

    # --- Shutdown ---
    if not backfill_task.done():
        backfill_task.cancel()
    if perf_task is not None:
        from app.services.perf_writer import flush_collector

        perf_task.cancel()
        perf_collector.enabled = False
        # Дописать текущую минуту; ни сбой, ни зависшая база не должны мешать остановке.
        try:
            await asyncio.wait_for(
                asyncio.to_thread(flush_collector, perf_collector, SessionLocal), timeout=10,
            )
        except Exception as exc:
            logger.warning("perf: замеры последней минуты не записаны: %s", exc)
    sched_svc.shutdown()
    watchdog_stop.set()
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Сервис для анализа Jira и квартального планирования",
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    # Браузер берёт имя скачиваемого файла из этого заголовка (в dev фронт на другом порту).
    expose_headers=["Content-Disposition"],
)

# Замеры быстродействия — снаружи остальных слоёв: время запроса целиком.
app.add_middleware(PerfMiddleware, collector=perf_collector)
app.add_middleware(RequestScopeMiddleware)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(ConditionError)
async def kpi_condition_error_handler(request, exc: ConditionError) -> JSONResponse:
    """Опечатка в условиях метрики KPI — понятный 422, а не 500.

    Срабатывает и при сохранении метрики в настройках (валидация вызывается
    явно), и при чтении уже сохранённых данных для отчёта — раздел считает
    премии, тихо проглатывать такие ошибки нельзя (см. ревью Фазы 3, BLOCKER 2).
    """
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(SyncBlockedError)
async def sync_blocked_handler(request, exc: SyncBlockedError) -> JSONResponse:
    """Синхронизация остановлена до переезда на новую Jira — 409 с понятным текстом."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


#: Postgres: не дождались чужой блокировки строки (предел ожидания lock_timeout).
LOCK_NOT_AVAILABLE = "55P03"


@app.exception_handler(OperationalError)
async def db_lock_timeout_handler(request, exc: OperationalError) -> JSONResponse:
    """Строку держит синхронизация или чужая правка дольше предела ожидания — 409.

    Незакреплённая часть записи откатывается (сессия закрывается без фиксации);
    действия с одной фиксацией повторять безопасно. Случай пишется в «Ошибки
    сервиса»: частые отказы — повод разбираться, кто держит строки. Остальные
    сбои базы — обычная 500.
    """
    if getattr(exc.orig, "pgcode", None) != LOCK_NOT_AVAILABLE:
        raise exc
    entry_id = error_log.record(request, exc)
    logger.warning(
        "Не дождались блокировки в базе: %s %s (номер %s)", request.method, request.url.path, entry_id,
    )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": "Эти данные сейчас обновляет синхронизация или другой пользователь. Повторите через минуту.",
            "error_id": entry_id,
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc: Exception) -> JSONResponse:
    """Необработанная ошибка — в кольцевой буфер для админской страницы.

    Без этого разбор любого 500 на проде упирался в консоль сервера: журнал
    контейнера доступен только системному администратору.
    """
    entry_id = error_log.record(request, exc)
    logger.exception(
        "Необработанная ошибка %s %s (номер %s)",
        request.method, request.url.path, entry_id,
    )
    # Этот обработчик работает снаружи CORSMiddleware — без своих заголовков
    # браузер режет ответ и фронт видит «Failed to fetch» вместо 500.
    origin = request.headers.get("origin")
    headers = (
        {"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true", "Vary": "Origin"}
        if origin in settings.cors_origins
        else None
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера", "error_id": entry_id},
        headers=headers,
    )


@app.get("/health")
async def health_check():
    """Жив ли сервис — без базы.

    Отвечает прямо из цикла обработки запросов: не ответил — цикл стоит,
    сервис не обслуживает никого. Внешний контроль смотрит сюда.
    """
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health/ready")
def health_ready():
    """Готов ли сервис работать с базой.

    Обычная функция — выполняется в рабочем потоке: медленная база не
    останавливает остальные запросы. Docker-проверка смотрит сюда и только
    помечает контейнер «unhealthy» — сам Docker такой контейнер не
    перезапускает. Зависший цикл перезапускает сторож (app/core/loop_watchdog.py).
    """
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("health_ready: db check failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "db_unavailable"},
        )
    finally:
        db.close()


class SPAStaticFiles(StaticFiles):
    def __init__(self, *args, **kwargs):
        self._spa_fallback = kwargs.pop("html", False)
        super().__init__(*args, html=False, **kwargs)

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            normalized = path.replace("\\", "/").lstrip("/")
            if (
                exc.status_code != 404
                or not self._spa_fallback
                or normalized.startswith("assets/")
                or not self._accepts_html(scope)
            ):
                raise
            return await super().get_response("index.html", scope)

    def _accepts_html(self, scope) -> bool:
        headers = dict(scope.get("headers") or [])
        accept = headers.get(b"accept", b"").decode("latin-1")
        return "text/html" in accept or "*/*" in accept


# --- Serve built frontend (SPA) ---
# Vite builds to frontend/dist; Docker image copies it to app/static.
# Mount LAST so explicit routes (above) take precedence.
_STATIC_DIR = Path(__file__).parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", SPAStaticFiles(directory=_STATIC_DIR, html=True), name="spa")
else:
    logger.info("Static SPA directory %s does not exist — running API-only", _STATIC_DIR)
