"""Cron-job entry: свернуть вчерашний день и подчистить старые события."""
from datetime import datetime, timedelta

import pytest

from app.jobs.aggregate_usage import aggregate_usage_job
from app.models import UsageDaily, UsageEvent, UsageEventType, User, UserRole


@pytest.fixture
def user(db_session):
    u = User(
        email="cron@test", password_hash="x", display_name="Cron",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    return u


def test_aggregate_usage_job_processes_yesterday(db_session, user):
    yesterday = datetime.utcnow() - timedelta(days=1)
    db_session.add(UsageEvent(
        user_id=user.id, event_type=UsageEventType.page_view,
        path="/dashboard", at=yesterday,
    ))
    db_session.commit()

    aggregate_usage_job(_session_factory=lambda: db_session)

    rows = db_session.query(UsageDaily).all()
    assert len(rows) == 1
    assert rows[0].date == yesterday.date()
