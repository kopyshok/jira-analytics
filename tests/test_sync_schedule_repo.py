"""Tests for SyncScheduleRepository."""

import pytest

from app.repositories.sync_schedule import SyncScheduleRepository


def _seed_defaults(repo: SyncScheduleRepository) -> None:
    """Seed the same defaults that migration 035 inserts."""
    repo.create(name="daily_incremental", cron_expr="0 6 * * *", mode="normal")
    repo.create(name="worklogs_workhours", cron_expr="0 8-20/2 * * 1-5", mode="quick")
    repo.create(name="weekly_full", cron_expr="0 3 * * 0", mode="full")


def test_list_returns_seeded_defaults(db_session):
    # Сиды добавляются вручную, т.к. тестовая БД — :memory: без миграций
    repo = SyncScheduleRepository(db_session)
    _seed_defaults(repo)
    items = repo.list_all()
    names = {i.name for i in items}
    assert {"daily_incremental", "worklogs_workhours", "weekly_full"}.issubset(names)


def test_update_changes_cron_and_enabled(db_session):
    repo = SyncScheduleRepository(db_session)
    _seed_defaults(repo)
    item = repo.list_all()[0]
    repo.update(item.id, cron_expr="0 7 * * *", enabled=False)
    db_session.refresh(item)
    assert item.cron_expr == "0 7 * * *"
    assert item.enabled is False


def test_create_and_delete(db_session):
    repo = SyncScheduleRepository(db_session)
    new = repo.create(name="custom_team", cron_expr="*/30 * * * *", mode="team", team="QA")
    assert new.id is not None
    repo.delete(new.id)
    assert repo.get(new.id) is None
