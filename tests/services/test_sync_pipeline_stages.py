"""Tests for pipeline stage wrappers."""
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.sync_pipeline import (
    CalendarStage,
    IssuesFullStage,
    IssuesIncrementalStage,
    IssuesRefreshByKeysStage,
    MappingStage,
    ProjectsStage,
    WorklogsDeltaStage,
    WorklogsFullStage,
)


@pytest.mark.asyncio
async def test_projects_stage_calls_sync_service():
    sync_svc = MagicMock(sync_projects=AsyncMock(return_value=5))
    stage = ProjectsStage(sync_svc)
    result = await stage.run({})
    sync_svc.sync_projects.assert_awaited_once()
    assert result["count"] == 5


@pytest.mark.asyncio
async def test_issues_incremental_stage():
    sync_svc = MagicMock(sync_issues=AsyncMock(return_value=12))
    stage = IssuesIncrementalStage(sync_svc)
    result = await stage.run({})
    sync_svc.sync_issues.assert_awaited_once_with(incremental=True)
    assert result["updated"] == 12


@pytest.mark.asyncio
async def test_issues_full_stage():
    sync_svc = MagicMock(sync_issues=AsyncMock(return_value=50))
    stage = IssuesFullStage(sync_svc)
    result = await stage.run({})
    sync_svc.sync_issues.assert_awaited_once_with(incremental=False)
    assert result["updated"] == 50


@pytest.mark.asyncio
async def test_calendar_stage_calls_sync_year():
    # sync_year is async
    calendar_svc = MagicMock(sync_year=AsyncMock(return_value=MagicMock(inserted=365)))
    stage = CalendarStage(calendar_svc, year=2026)
    result = await stage.run({})
    calendar_svc.sync_year.assert_awaited_once_with(2026)
    assert result["year"] == 2026
    assert result["days_inserted"] == 365


@pytest.mark.asyncio
async def test_worklogs_delta_uses_since_from_ctx():
    """WorklogsDeltaStage passes since from ctx to service."""
    fake_stats = MagicMock(worklogs_upserted=10, issue_keys=[])
    sync_svc = MagicMock(update_worklogs_since=AsyncMock(return_value=fake_stats))
    ctx = {"since": "2026-04-01"}
    stage = WorklogsDeltaStage(sync_svc)
    result = await stage.run(ctx)
    sync_svc.update_worklogs_since.assert_awaited_once()
    call_kwargs = sync_svc.update_worklogs_since.call_args[1]
    assert call_kwargs["since"] == date(2026, 4, 1)
    assert result["worklogs_upserted"] == 10


@pytest.mark.asyncio
async def test_worklogs_delta_sets_default_since_when_missing():
    """WorklogsDeltaStage sets default since (7 days ago) if not in ctx."""
    fake_stats = MagicMock(worklogs_upserted=3, issue_keys=[])
    sync_svc = MagicMock(update_worklogs_since=AsyncMock(return_value=fake_stats))
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run({})
    sync_svc.update_worklogs_since.assert_awaited_once()
    call_kwargs = sync_svc.update_worklogs_since.call_args[1]
    assert "since" in call_kwargs


@pytest.mark.asyncio
async def test_issues_refresh_by_keys_uses_ctx_keys():
    sync_svc = MagicMock(refresh_issues_by_keys=AsyncMock(return_value=(2, 2)))
    stage = IssuesRefreshByKeysStage(sync_svc)
    ctx = {"touched_issue_keys": ["A-1", "A-2"]}
    await stage.run(ctx)
    sync_svc.refresh_issues_by_keys.assert_awaited_once_with(jira_keys=["A-1", "A-2"])


@pytest.mark.asyncio
async def test_issues_refresh_skips_when_no_keys():
    sync_svc = MagicMock(refresh_issues_by_keys=AsyncMock())
    stage = IssuesRefreshByKeysStage(sync_svc)
    result = await stage.run({})
    sync_svc.refresh_issues_by_keys.assert_not_awaited()
    assert result["refreshed"] == 0


@pytest.mark.asyncio
async def test_mapping_stage_subset_when_ids_in_ctx():
    mapping_svc = MagicMock(recalculate_for_issues=MagicMock(return_value=3))
    stage = MappingStage(mapping_svc)
    ctx = {"touched_issue_ids": ["i1", "i2"]}
    result = await stage.run(ctx)
    mapping_svc.recalculate_for_issues.assert_called_once_with(["i1", "i2"])
    assert result["affected"] == 3


@pytest.mark.asyncio
async def test_mapping_stage_full_when_no_ids():
    fake_stats = MagicMock(issues_processed=10)
    mapping_svc = MagicMock(recalculate_all=MagicMock(return_value=fake_stats))
    stage = MappingStage(mapping_svc)
    result = await stage.run({})
    mapping_svc.recalculate_all.assert_called_once()
    assert result["affected"] == 10
