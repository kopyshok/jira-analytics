"""FastAPI application entry point."""

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Debug mode: {settings.debug}")
    print(f"Database: {settings.database_url}")

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
    print("Shutting down...")


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
    allow_methods=["*"],
    allow_headers=["*"],
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
