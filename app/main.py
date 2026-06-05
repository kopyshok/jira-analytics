"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.api.router import api_router
from app.database import SessionLocal
from app.repositories.sync_schedule import SyncScheduleRepository
from app.services.scheduler import SchedulerService, scheduled_pipeline_runner
from app.jobs.aggregate_usage import aggregate_usage_job
from app.jobs.regenerate_summaries import regenerate_outdated_summaries
from apscheduler.triggers.cron import CronTrigger

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    logger.info("Debug mode: %s", settings.debug)
    logger.info("Database: %s", settings.database_url)

    # --- Release notes seed from release_notes/*.json ---
    db = SessionLocal()
    try:
        from app.services.release_note_seed import seed_from_files
        try:
            seed_from_files(db)
        except Exception as e:
            logger.warning("release_notes seed failed (non-fatal): %s", e)
    finally:
        db.close()

    # --- Scheduler ---
    db = SessionLocal()
    try:
        schedules = SyncScheduleRepository(db).list_all()
    finally:
        db.close()

    sched_svc = SchedulerService(trigger_runner=scheduled_pipeline_runner)
    sched_svc.register_jobs(schedules)
    sched_svc.start()
    sched_svc.scheduler.add_job(
        regenerate_outdated_summaries,
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
    app.state.scheduler = sched_svc

    # --- Embedding model warmup (background, non-blocking) ---
    async def _warmup_embedding() -> None:
        try:
            from app.services.llm.embedding_service import EmbeddingService
            await asyncio.to_thread(EmbeddingService().warmup)
            logger.info("Embedding service warmed up")
        except Exception as e:
            logger.warning("Embedding warmup failed (non-fatal): %s", e)

    warmup_task = asyncio.create_task(_warmup_embedding())
    app.state.embedding_warmup_task = warmup_task

    yield

    # --- Shutdown ---
    if not warmup_task.done():
        warmup_task.cancel()
    sched_svc.shutdown()
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
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Liveness probe — does NOT touch the database.

    External uptime monitors should hit this. Always returns 200 while
    the process is up, regardless of DB state.
    """
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — verifies the database is reachable.

    Used by the Docker healthcheck so the container is restarted if DB
    connectivity is lost.
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
