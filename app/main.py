"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.api.router import api_router
from app.database import SessionLocal
from app.repositories.sync_schedule import SyncScheduleRepository
from app.services.scheduler import SchedulerService, scheduled_pipeline_runner
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
    app.state.scheduler = sched_svc

    yield

    # --- Shutdown ---
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
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }
