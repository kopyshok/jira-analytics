"""Tests for SchedulerService (T19)."""

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from app.services.scheduler import SchedulerService


# ------------------------------------------------------------------
# T19-a: cron validation
# ------------------------------------------------------------------

def test_validates_cron_expression():
    assert SchedulerService.is_valid_cron("0 6 * * *") is True
    assert SchedulerService.is_valid_cron("0 8-20/2 * * 1-5") is True
    assert SchedulerService.is_valid_cron("not a cron") is False
    assert SchedulerService.is_valid_cron("") is False


# ------------------------------------------------------------------
# T19-b: next_run_at
# ------------------------------------------------------------------

def test_compute_next_run():
    nxt = SchedulerService.next_run_at("0 6 * * *")
    assert nxt is not None
    assert isinstance(nxt, datetime)
    # следующий запуск должен быть в будущем
    from datetime import timezone
    assert nxt > datetime.now(tz=timezone.utc)

    assert SchedulerService.next_run_at("not valid") is None


# ------------------------------------------------------------------
# T19-c: register_jobs creates one job per enabled schedule
# ------------------------------------------------------------------

def test_register_jobs_creates_one_per_enabled_schedule():
    mock_scheduler = MagicMock()
    mock_runner = MagicMock()

    svc = SchedulerService(scheduler=mock_scheduler, trigger_runner=mock_runner)

    enabled1 = MagicMock()
    enabled1.id = "s1"
    enabled1.enabled = True
    enabled1.cron_expr = "0 6 * * *"
    enabled1.mode = "normal"
    enabled1.team = None

    enabled2 = MagicMock()
    enabled2.id = "s2"
    enabled2.enabled = True
    enabled2.cron_expr = "0 3 * * 0"
    enabled2.mode = "full"
    enabled2.team = None

    disabled = MagicMock()
    disabled.id = "s3"
    disabled.enabled = False
    disabled.cron_expr = "0 8 * * *"
    disabled.mode = "quick"
    disabled.team = None

    svc.register_jobs([enabled1, enabled2, disabled])

    mock_scheduler.remove_all_jobs.assert_called_once()
    assert mock_scheduler.add_job.call_count == 2

    # проверяем что disabled не зарегистрирован
    job_ids = [c.kwargs["id"] for c in mock_scheduler.add_job.call_args_list]
    assert "s1" in job_ids
    assert "s2" in job_ids
    assert "s3" not in job_ids
