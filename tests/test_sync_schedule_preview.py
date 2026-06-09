"""Тесты humanize_cron + next_runs + preview endpoint."""
from datetime import datetime

import pytest

from app.services.scheduler import SchedulerService


class TestHumanizeCron:
    def test_every_5_minutes(self):
        assert SchedulerService.humanize_cron("*/5 * * * *") == "Каждые 5 минут"

    def test_every_minute(self):
        assert SchedulerService.humanize_cron("*/1 * * * *") == "Каждую минуту"

    def test_every_2_hours(self):
        assert SchedulerService.humanize_cron("0 */2 * * *") == "Каждые 2 часа"

    def test_every_hour(self):
        assert SchedulerService.humanize_cron("0 */1 * * *") == "Каждый час"

    def test_every_6_hours(self):
        assert SchedulerService.humanize_cron("0 */6 * * *") == "Каждые 6 часов"

    def test_daily(self):
        assert SchedulerService.humanize_cron("0 6 * * *") == "Каждый день в 06:00"

    def test_daily_with_minutes(self):
        assert SchedulerService.humanize_cron("30 9 * * *") == "Каждый день в 09:30"

    def test_weekdays_range(self):
        assert SchedulerService.humanize_cron("30 9 * * 1-5") == "По будням (пн-пт) в 09:30"

    def test_weekdays_list(self):
        assert (
            SchedulerService.humanize_cron("30 9 * * 1,2,3,4,5")
            == "По будням (пн-пт) в 09:30"
        )

    def test_weekends(self):
        assert SchedulerService.humanize_cron("0 10 * * 0,6") == "По выходным (сб-вс) в 10:00"

    def test_specific_days(self):
        # пн + чт = 1,4
        assert SchedulerService.humanize_cron("0 18 * * 1,4") == "По дням: пн, чт в 18:00"

    def test_weekly_single_day_wednesday(self):
        assert SchedulerService.humanize_cron("0 12 * * 3") == "Каждую среду в 12:00"

    def test_weekly_friday(self):
        assert SchedulerService.humanize_cron("0 18 * * 5") == "Каждую пятницу в 18:00"

    def test_unparseable_fallback(self):
        # сложное cron-выражение не из шаблона
        result = SchedulerService.humanize_cron("15,45 8-17 * * *")
        assert result.startswith("По cron-выражению:")

    def test_malformed_fallback(self):
        result = SchedulerService.humanize_cron("not a cron")
        assert result.startswith("По cron-выражению:")


class TestNextRuns:
    def test_daily_returns_3(self):
        runs = SchedulerService.next_runs("0 6 * * *", count=3)
        assert len(runs) == 3
        for i in range(1, 3):
            delta = runs[i] - runs[i - 1]
            assert delta.total_seconds() == 86400

    def test_every_5_minutes(self):
        runs = SchedulerService.next_runs("*/5 * * * *", count=3)
        assert len(runs) == 3
        for i in range(1, 3):
            delta = runs[i] - runs[i - 1]
            assert delta.total_seconds() == 300

    def test_returns_aware_datetimes(self):
        runs = SchedulerService.next_runs("0 6 * * *", count=1)
        assert len(runs) == 1
        assert runs[0].tzinfo is not None

    def test_invalid_cron_returns_empty(self):
        assert SchedulerService.next_runs("not a cron", count=3) == []
