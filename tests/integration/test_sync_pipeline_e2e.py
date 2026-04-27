"""Integration: pipeline на seeded e2e.db, без реальных Jira-вызовов.

Использует data/e2e.db (создаётся scripts/seed_e2e.py).
Изолированная фикстура — не использует общий conftest db_session,
чтобы не нарушать cleanup инвариант тестовой in-memory БД.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


E2E_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "e2e.db")


@pytest.fixture(scope="function")
def e2e_db_session():
    """Session on data/e2e.db — изолирована от основного in-memory engine.

    Создаёт таблицы sync_run/sync_schedule если их нет (e2e.db может быть
    на старой миграции), чтобы тест работал без полного alembic upgrade.
    """
    db_path = os.path.abspath(E2E_DB_PATH)
    if not os.path.exists(db_path):
        pytest.skip(f"e2e.db not found at {db_path}; run scripts/seed_e2e.py first")

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    # Ensure sync_run and sync_schedule tables exist (may be missing on old e2e.db)
    import app.models  # noqa: ensure all models are registered
    from app.database import Base
    from app.models.sync_run import SyncRun
    from app.models.sync_schedule import SyncSchedule

    with engine.begin() as conn:
        # Create only the tables needed for this test
        SyncRun.__table__.create(conn, checkfirst=True)
        SyncSchedule.__table__.create(conn, checkfirst=True)

    TestingSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.rollback()
        # Clean up sync_run rows created during the test
        with engine.begin() as conn:
            conn.execute(SyncRun.__table__.delete())
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_pipeline_normal_mode_writes_sync_run(e2e_db_session):
    from app.repositories.sync_run import SyncRunRepository
    from app.services.event_bus import EventBroadcaster
    from app.services.mapping_service import MappingService
    from app.services.production_calendar_service import ProductionCalendarService
    from app.services.sync_pipeline import PipelineOrchestrator, build_pipeline
    from app.services.sync_service import SyncService

    # SyncService requires a JiraClient — use a mock
    mock_jira = MagicMock()
    fake_update_stats = MagicMock(worklogs_upserted=0)
    fake_update_stats.issue_keys = []
    fake_calendar_result = MagicMock(inserted=0)
    fake_mapping_stats = MagicMock(issues_processed=0)

    # Mock all network calls — we only test the orchestration logic
    with patch.object(SyncService, "sync_projects", AsyncMock(return_value=0)), \
         patch.object(SyncService, "sync_issues", AsyncMock(return_value=0)), \
         patch.object(SyncService, "update_worklogs_since", AsyncMock(return_value=fake_update_stats)), \
         patch.object(ProductionCalendarService, "sync_year", AsyncMock(return_value=fake_calendar_result)), \
         patch.object(MappingService, "recalculate_all", lambda self: fake_mapping_stats):

        services = {
            "sync": SyncService(e2e_db_session, mock_jira),
            "calendar": ProductionCalendarService(e2e_db_session),
            "mapping": MappingService(e2e_db_session),
        }
        stages = build_pipeline(mode="normal", services=services)
        bus = EventBroadcaster()
        repo = SyncRunRepository(e2e_db_session)
        run = repo.create(mode="normal", trigger="manual")
        orch = PipelineOrchestrator(stages, db=e2e_db_session, bus=bus)
        result = await orch.run(mode="normal", trigger="manual", run_id=run.id)
        repo.finalize(run.id, status=result["status"], stages=result["stages"])

    e2e_db_session.refresh(run)
    assert run.status == "ok"
    assert len(run.stages_json) == 5  # calendar + projects + issues + worklogs + mapping
