"""Tests for pipeline stage wrappers."""
from datetime import date, datetime
from types import SimpleNamespace
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


def _make_sync_svc(**kwargs):
    """MagicMock с предустановленным _get_sync_state=None (нет cursor)."""
    defaults = dict(
        _get_sync_state=MagicMock(return_value=None),
        _update_sync_state=MagicMock(),
    )
    defaults.update(kwargs)
    return MagicMock(**defaults)


@pytest.mark.asyncio
async def test_worklogs_delta_uses_since_from_ctx():
    """WorklogsDeltaStage passes since from ctx to service."""
    fake_stats = SimpleNamespace(worklogs_upserted=10, touched_issue_keys=set())
    sync_svc = _make_sync_svc(update_worklogs_v2=AsyncMock(return_value=fake_stats))
    ctx = {"since": "2026-04-01"}
    stage = WorklogsDeltaStage(sync_svc)
    result = await stage.run(ctx)
    sync_svc.update_worklogs_v2.assert_awaited_once()
    call_kwargs = sync_svc.update_worklogs_v2.call_args[1]
    assert call_kwargs["since"] == date(2026, 4, 1)
    assert result["worklogs_upserted"] == 10


@pytest.mark.asyncio
async def test_worklogs_delta_sets_default_since_when_missing():
    """WorklogsDeltaStage sets default since (7 days ago) if not in ctx."""
    fake_stats = SimpleNamespace(worklogs_upserted=3, touched_issue_keys=set())
    sync_svc = _make_sync_svc(update_worklogs_v2=AsyncMock(return_value=fake_stats))
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run({})
    sync_svc.update_worklogs_v2.assert_awaited_once()
    call_kwargs = sync_svc.update_worklogs_v2.call_args[1]
    assert "since" in call_kwargs


@pytest.mark.asyncio
async def test_worklogs_delta_collects_keys_into_ctx():
    """WorklogsDeltaStage reads touched_issue_keys from UpdateStats and sets ctx."""
    fake_stats = SimpleNamespace(
        worklogs_upserted=5,
        touched_issue_keys={"A-1", "A-2"},
    )
    sync_svc = _make_sync_svc(update_worklogs_v2=AsyncMock(return_value=fake_stats))
    ctx: dict = {}
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run(ctx)
    assert set(ctx.get("touched_issue_keys", [])) == {"A-1", "A-2"}


@pytest.mark.asyncio
async def test_worklogs_delta_no_ctx_when_keys_empty():
    """WorklogsDeltaStage does not set touched_issue_keys in ctx when set is empty."""
    fake_stats = SimpleNamespace(worklogs_upserted=0, touched_issue_keys=set())
    sync_svc = _make_sync_svc(update_worklogs_v2=AsyncMock(return_value=fake_stats))
    ctx: dict = {}
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run(ctx)
    assert "touched_issue_keys" not in ctx


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


@pytest.mark.asyncio
async def test_mapping_stage_resolves_keys_to_ids_via_db_lookup():
    """MappingStage конвертирует touched_issue_keys → ids через DB lookup."""
    uuid1, uuid2 = "uuid-aaa", "uuid-bbb"

    # Мокаем цепочку db.query(...).filter(...).all()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_filter.all.return_value = [(uuid1,), (uuid2,)]
    mock_query.filter.return_value = mock_filter

    mapping_svc = MagicMock(
        db=MagicMock(query=MagicMock(return_value=mock_query)),
        recalculate_for_issues=MagicMock(return_value=2),
    )
    stage = MappingStage(mapping_svc)
    ctx: dict = {"touched_issue_keys": ["A-1", "A-2"]}
    result = await stage.run(ctx)

    mapping_svc.recalculate_for_issues.assert_called_once_with([uuid1, uuid2])
    mapping_svc.recalculate_all.assert_not_called()
    assert result["affected"] == 2


@pytest.mark.asyncio
async def test_mapping_stage_full_when_no_keys_and_no_ids():
    """Нет ни ids, ни keys → full recalc."""
    fake_stats = MagicMock(issues_processed=10)
    mapping_svc = MagicMock(recalculate_all=MagicMock(return_value=fake_stats))
    stage = MappingStage(mapping_svc)
    result = await stage.run({})
    mapping_svc.recalculate_all.assert_called_once()
    mapping_svc.recalculate_for_issues.assert_not_called()
    assert result["affected"] == 10


# ──────────────────────── cursor tests ────────────────────────

@pytest.mark.asyncio
async def test_worklogs_delta_uses_sync_state_cursor():
    """Если в sync_state есть cursor (3 дня назад), since = max(cursor-24h, today-7d).

    При cursor 3 дня назад, overlap_since = cursor - 1d = 4 дня назад.
    4 дня назад > today - 7d → since = 4 дня назад (cursor доминирует).
    """
    from datetime import timedelta
    cursor_dt = datetime.utcnow() - timedelta(days=3)
    cursor_state = SimpleNamespace(last_success_at=cursor_dt)

    fake_stats = SimpleNamespace(worklogs_upserted=0, touched_issue_keys=set())
    sync_svc = _make_sync_svc(
        _get_sync_state=MagicMock(return_value=cursor_state),
        update_worklogs_v2=AsyncMock(return_value=fake_stats),
    )
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run({})

    call_kwargs = sync_svc.update_worklogs_v2.call_args[1]
    actual_since: date = call_kwargs["since"]
    # since должен быть cursor - 1d (в date), не today-7d
    expected_since = (cursor_dt - timedelta(hours=24)).date()
    assert actual_since == expected_since


@pytest.mark.asyncio
async def test_worklogs_delta_uses_fallback_when_no_cursor():
    """Без cursor since = today - 7d."""
    from datetime import timedelta
    fake_stats = SimpleNamespace(worklogs_upserted=0, touched_issue_keys=set())
    sync_svc = _make_sync_svc(
        _get_sync_state=MagicMock(return_value=None),
        update_worklogs_v2=AsyncMock(return_value=fake_stats),
    )
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run({})

    call_kwargs = sync_svc.update_worklogs_v2.call_args[1]
    actual_since: date = call_kwargs["since"]
    assert actual_since == date.today() - timedelta(days=7)


@pytest.mark.asyncio
async def test_worklogs_delta_writes_sync_state_after_run():
    """После успешного update_worklogs_v2 вызывается _update_sync_state."""
    fake_stats = SimpleNamespace(worklogs_upserted=2, touched_issue_keys={"K-1"})
    sync_svc = _make_sync_svc(
        update_worklogs_v2=AsyncMock(return_value=fake_stats),
    )
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run({})

    sync_svc._update_sync_state.assert_called_once()
    call_args = sync_svc._update_sync_state.call_args
    # entity_name = "worklogs", scope = ""
    assert call_args[0][0] == "worklogs" or call_args[1].get("entity_name") == "worklogs"
    scope = call_args[1].get("scope", call_args[0][2] if len(call_args[0]) > 2 else "")
    assert scope == ""


@pytest.mark.asyncio
async def test_worklogs_delta_explicit_since_skips_cursor():
    """Явный since из ctx не читает cursor из sync_state."""
    fake_stats = SimpleNamespace(worklogs_upserted=0, touched_issue_keys=set())
    sync_svc = _make_sync_svc(
        update_worklogs_v2=AsyncMock(return_value=fake_stats),
    )
    stage = WorklogsDeltaStage(sync_svc)
    await stage.run({"since": "2026-01-01"})

    # _get_sync_state не должен быть вызван (explicit since)
    sync_svc._get_sync_state.assert_not_called()
    call_kwargs = sync_svc.update_worklogs_v2.call_args[1]
    assert call_kwargs["since"] == date(2026, 1, 1)
