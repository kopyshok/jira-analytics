"""ProjectSummaryService: cache hit/miss + force regenerate."""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.issue import Issue
from app.models.project import Project
from app.models.project_ai_summary import ProjectAISummary
from app.services.llm.types import ProjectSummary, ChecklistItem, WorkBreakdownGroup
from app.services.project_summary_service import ProjectSummaryService


@pytest.fixture
def test_db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_epic(db, key="PRJ-1"):
    db.add(Project(id="p1", jira_project_id="10001", key="PRJ", name="P"))
    db.add(Issue(id="i1", jira_issue_id="1", key=key, summary="Test",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="quarterly_tasks", include_in_analysis=True))
    db.commit()


@pytest.mark.asyncio
async def test_get_summary_returns_none_when_no_cache(test_db_session):
    _seed_epic(test_db_session)
    result = await ProjectSummaryService(test_db_session).get_summary("PRJ-1")
    assert result is None


@pytest.mark.asyncio
async def test_get_summary_returns_cached_row(test_db_session):
    db = test_db_session
    _seed_epic(db)
    cached = ProjectAISummary(
        issue_id="i1",
        goals_json=json.dumps(["a", "b", "c"], ensure_ascii=False),
        result_checklist_json=json.dumps(
            [{"label": "y", "done": True, "category": "analysis"}], ensure_ascii=False
        ),
        status_text="Cached", workload_summary="WS",
        generated_at=datetime.utcnow(), model_used="gemini-2.0-flash",
    )
    db.add(cached)
    db.commit()
    result = await ProjectSummaryService(db).get_summary("PRJ-1")
    assert result is not None
    assert result.status_text == "Cached"


@pytest.mark.asyncio
async def test_regenerate_calls_llm_and_writes_cache(test_db_session):
    db = test_db_session
    _seed_epic(db)
    fake = ProjectSummary(
        goals=["g1", "g2", "g3"],
        result_checklist=[ChecklistItem(label="ok", done=True, category="analysis")],
        status_text="ST", workload_summary="WS",
        work_breakdown=[
            WorkBreakdownGroup(bucket="analysis", label="Анализ", child_keys=["X-1"]),
        ],
    )
    fake_meta = {"input_tokens": 100, "output_tokens": 50, "model": "gemini-2.0-flash"}

    fake_provider = AsyncMock()
    fake_provider.summarize_project = AsyncMock(return_value=(fake, fake_meta))
    fake_provider.name = "gemini"
    fake_provider.model = "gemini-2.0-flash"

    with patch("app.services.project_summary_service.get_llm_provider", return_value=fake_provider):
        result = await ProjectSummaryService(db).regenerate("PRJ-1")

    assert result.status_text == "ST"
    assert result.input_tokens == 100
    saved = db.query(ProjectAISummary).filter_by(issue_id="i1").first()
    assert saved is not None
    assert json.loads(saved.goals_json) == ["g1", "g2", "g3"]


@pytest.mark.asyncio
async def test_regenerate_raises_for_unknown_key(test_db_session):
    db = test_db_session
    with pytest.raises(ValueError):
        await ProjectSummaryService(db).regenerate("UNKNOWN-1")
