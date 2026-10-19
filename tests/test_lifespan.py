"""Tests for lifespan scheduler startup (T21).

Используем patch вместо реальной БД, чтобы не трогать data/jira_analytics.db.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.main import app, lifespan


def _make_fake_schedules():
    """Вернуть 3 фейковых объекта SyncSchedule."""
    schedules = []
    data = [
        ("s1", "daily_incremental", "0 6 * * *", "normal"),
        ("s2", "worklogs_workhours", "0 8-20/2 * * 1-5", "quick"),
        ("s3", "weekly_full", "0 3 * * 0", "full"),
    ]
    for sid, name, cron, mode in data:
        s = MagicMock()
        s.id = sid
        s.name = name
        s.cron_expr = cron
        s.mode = mode
        s.team = None
        s.enabled = True
        schedules.append(s)
    return schedules


@pytest.mark.asyncio
async def test_lifespan_starts_scheduler_with_seeded_jobs():
    """lifespan стартует SchedulerService; если в БД есть enabled расписания — они регистрируются."""
    fake_schedules = _make_fake_schedules()

    with patch(
        "app.main.SyncScheduleRepository",
        autospec=True,
    ) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = fake_schedules
        mock_repo_cls.return_value = mock_repo

        async with lifespan(app):
            assert hasattr(app.state, "scheduler")
            sched_svc = app.state.scheduler
            assert sched_svc.scheduler.running is True

            jobs = sched_svc.scheduler.get_jobs()
            # 3 sync jobs + regenerate_summaries + aggregate_usage + renew_tokens
            assert len(jobs) == 6


@pytest.mark.asyncio
async def test_lifespan_registers_hourly_token_renewal():
    """lifespan ставит проверку токенов Jira/Confluence раз в час, без наложения запусков."""
    with patch("app.main.SyncScheduleRepository", autospec=True) as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.list_all.return_value = []
        mock_repo_cls.return_value = mock_repo

        async with lifespan(app):
            job = app.state.scheduler.scheduler.get_job("renew_tokens")
            assert job is not None
            assert job.max_instances == 1
            assert job.trigger.interval == timedelta(hours=1)
