"""Схемы на настоящих (обезличенных) ответах Jira DC: люди — по key, логин — name."""
from datetime import datetime

import pytest

from app.connectors.schemas import (
    JiraCommentSchema,
    JiraIssueSchema,
    JiraUserSchema,
    JiraWorklogSchema,
    JiraWorklogsResponseSchema,
)
from app.models import Comment, Employee, Issue, Project
from app.services.sync_service import SyncService, _author_as_user, _extract_user_field
from tests.dc_fixtures import load_dc


def test_dc_user_identity_is_key_and_login_is_name():
    raw = load_dc("user_search.json")[0]
    user = JiraUserSchema.model_validate(raw)
    assert user.jira_account_id == raw["key"]
    assert user.name == raw["name"]
    assert user.display_name == raw["displayName"]
    assert user.email == raw["emailAddress"]


def test_dc_issue_people_parse():
    raw = load_dc("issue_OS-91030.json")
    issue = JiraIssueSchema.model_validate(raw)
    assert issue.fields.assignee.jira_account_id == raw["fields"]["assignee"]["key"]
    assert issue.fields.reporter.name == raw["fields"]["reporter"]["name"]
    assert issue.fields.creator.display_name == raw["fields"]["creator"]["displayName"]


def test_dc_worklog_author_parses():
    raw = load_dc("worklogs_OS-91030.json")
    page = JiraWorklogsResponseSchema.model_validate(raw)
    wl = page.worklogs[0]
    assert wl.author.jira_account_id == raw["worklogs"][0]["author"]["key"]
    assert wl.author.name == raw["worklogs"][0]["author"]["name"]
    assert wl.issueId == raw["worklogs"][0]["issueId"]


def test_author_as_user_keeps_login_and_is_active():
    wl = JiraWorklogSchema.model_validate(load_dc("worklog_list.json")[0])
    user = _author_as_user(wl.author)
    assert user.jira_account_id == wl.author.jira_account_id
    assert user.name == wl.author.name
    assert user.display_name == wl.author.display_name
    assert user.is_active is True
    assert wl.author.avatar_url is not None
    assert user.avatar_url == wl.author.avatar_url


def test_legacy_inactive_user_without_email_and_avatar():
    """Старая учётка: key совпадает с логином, почты и аватара нет."""
    user = JiraUserSchema.model_validate(
        {"key": "olduser", "name": "olduser", "displayName": "Бывший сотрудник", "active": False}
    )
    assert user.jira_account_id == "olduser"
    assert user.name == "olduser"
    assert user.is_active is False
    assert user.email is None
    assert user.avatar_url is None


def test_developer_field_reads_key():
    fields = load_dc("issue_OS-91030.json")["fields"]
    account, name = _extract_user_field(fields, "customfield_11098")
    assert account == fields["customfield_11098"]["key"]
    assert name == fields["customfield_11098"]["displayName"]


def test_anonymous_comment_parses_without_author():
    comment = JiraCommentSchema.model_validate({"id": "1", "body": "текст"})
    assert comment.author is None


@pytest.mark.asyncio
async def test_sync_comments_stores_anonymous_comment_without_author(db_session):
    project = Project(
        id="p-1", jira_project_id="10000", key="PRJ", name="Test",
        synced_at=datetime.utcnow(),
    )
    issue = Issue(
        id="i-1", jira_issue_id="20000", key="PRJ-1", project_id=project.id,
        summary="s", issue_type="Task", status="Open", status_category="new",
        synced_at=datetime.utcnow(),
    )
    db_session.add_all([project, issue])
    db_session.commit()

    class FakeJira:
        async def iter_comments_for_issue(self, issue_id):
            yield JiraCommentSchema.model_validate(
                {"id": "c-1", "body": "текст", "created": "2026-10-01T10:00:00.000+0000"}
            )

    svc = SyncService(db_session, FakeJira())
    assert await svc.sync_comments() == 1
    assert svc.stats.errors == []
    comment = db_session.query(Comment).one()
    assert comment.author_id is None
    assert db_session.query(Employee).count() == 0
