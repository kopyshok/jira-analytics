"""Время ворклогов и комментариев хранится московским «настенным», как было в облаке."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.connectors.schemas import JiraWorklogsResponseSchema
from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService, _drop_tz
from tests.dc_fixtures import load_dc


def test_drop_tz_converts_utc_to_moscow():
    assert _drop_tz(datetime(2026, 9, 11, 7, 0, tzinfo=timezone.utc)) == datetime(2026, 9, 11, 10, 0)
    assert _drop_tz(datetime(2026, 9, 11, 22, 30, tzinfo=timezone.utc)) == datetime(2026, 9, 12, 1, 30)


def test_drop_tz_keeps_moscow_and_naive():
    msk = timezone(timedelta(hours=3))
    assert _drop_tz(datetime(2026, 7, 24, 10, 0, tzinfo=msk)) == datetime(2026, 7, 24, 10, 0)
    assert _drop_tz(datetime(2026, 7, 24, 10, 0)) == datetime(2026, 7, 24, 10, 0)
    assert _drop_tz(None) is None


def test_dc_worklog_stored_in_moscow_time(db_session):
    db_session.add(Project(id="p-os", jira_project_id="10901", key="OS", name="1С"))
    db_session.add(Issue(id="i1", jira_issue_id="258783", key="OS-91030", summary="s",
                         issue_type="Задача", status="В работе", project_id="p-os"))
    db_session.add(Employee(id="e1", jira_account_id="JIRAUSER90001",
                            display_name="Сотрудник 1", is_active=True))
    db_session.commit()
    wl = JiraWorklogsResponseSchema.model_validate(load_dc("worklogs_OS-91030.json")).worklogs[0]
    assert wl.started == "2026-09-11T07:00:00.000+0000"

    SyncService(db_session, MagicMock())._upsert_worklog(wl, "i1", "e1")
    db_session.commit()

    stored = db_session.query(Worklog).filter_by(jira_worklog_id=wl.id).one()
    assert stored.started_at == datetime(2026, 9, 11, 10, 0)
