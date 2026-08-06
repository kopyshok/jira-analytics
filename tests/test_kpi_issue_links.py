"""Связи задач сохраняются и позволяют найти автора связанной задачи."""
from unittest.mock import MagicMock

import pytest

from app.connectors.schemas import (
    JiraIssueFieldsSchema,
    JiraIssueSchema,
    JiraIssueTypeSchema,
    JiraProjectSchema,
    JiraStatusSchema,
)
from app.models.issue_link import IssueLink
from app.models.project import Project
from app.services.sync_service import SyncService


def test_issue_link_roundtrip(db_session):
    from app.models.issue import Issue

    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()

    task = Issue(jira_issue_id="1", key="OS-10", summary="Задача", issue_type="Задача",
                 status="ГОТОВО", project_id=project.id, reporter_account_id="acc-1")
    bug = Issue(jira_issue_id="2", key="OS-11", summary="Баг", issue_type="Баг",
                status="ГОТОВО", project_id=project.id)
    db_session.add_all([task, bug])
    db_session.commit()

    db_session.add(IssueLink(
        source_issue_id=bug.id, target_issue_id=task.id, link_type="Relates",
    ))
    db_session.commit()

    linked = (
        db_session.query(Issue)
        .join(IssueLink, IssueLink.target_issue_id == Issue.id)
        .filter(IssueLink.source_issue_id == bug.id)
        .one()
    )
    assert linked.reporter_account_id == "acc-1"


def _issue_schema(jira_id: str, key: str, project_id: str, *, issuelinks=None, created=None):
    """Минимальная JiraIssueSchema для прогона через SyncService.sync_issues."""
    return JiraIssueSchema(
        id=jira_id,
        key=key,
        fields=JiraIssueFieldsSchema(
            summary=f"Issue {key}",
            issuetype=JiraIssueTypeSchema(id="1", name="Задача", subtask=False),
            status=JiraStatusSchema(id="1", name="Open"),
            project=JiraProjectSchema(id=project_id, key="OS", name="1С"),
            issuelinks=issuelinks,
            created=created,
        ),
    )


@pytest.mark.asyncio
async def test_sync_issues_removes_link_when_jira_sends_empty_issuelinks(db_session):
    """BLOCKER 1: пустой issuelinks из Jira — это снятие связи, а не «поле не пришло».

    Задача разлинкована в Jira (последнюю связь убрали) → Jira отдаёт
    ``issuelinks: []``. Локальная строка связи должна исчезнуть, иначе
    отвязанный баг бессрочно продолжит считаться против аналитика.
    """
    from app.models.issue import Issue

    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()

    source = Issue(jira_issue_id="100", key="OS-100", summary="Баг", issue_type="Баг",
                    status="Open", project_id=project.id)
    target = Issue(jira_issue_id="101", key="OS-101", summary="Задача", issue_type="Задача",
                    status="Open", project_id=project.id)
    db_session.add_all([source, target])
    db_session.commit()
    db_session.add(IssueLink(source_issue_id=source.id, target_issue_id=target.id, link_type="Relates"))
    db_session.commit()

    schema = _issue_schema("100", "OS-100", "p-1", issuelinks=[])

    mock_jira = MagicMock()

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        yield schema

    mock_jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, mock_jira)
    await svc.sync_issues(project_keys=["OS"], incremental=False)

    remaining = db_session.query(IssueLink).filter(IssueLink.source_issue_id == source.id).all()
    assert remaining == []


@pytest.mark.asyncio
async def test_sync_issues_dedupes_duplicate_link_pairs(db_session):
    """BLOCKER 2: Jira отдаёт обе стороны одной связи одного типа — не дублируем строку."""
    from app.models.issue import Issue

    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()

    target = Issue(jira_issue_id="201", key="OS-201", summary="Задача", issue_type="Задача",
                    status="Open", project_id=project.id)
    db_session.add(target)
    db_session.commit()

    duplicate_links = [
        {"type": {"name": "Relates"}, "outwardIssue": {"id": "201"}},
        {"type": {"name": "Relates"}, "inwardIssue": {"id": "201"}},
    ]
    schema = _issue_schema("200", "OS-200", "p-1", issuelinks=duplicate_links)

    mock_jira = MagicMock()

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        yield schema

    mock_jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, mock_jira)
    await svc.sync_issues(project_keys=["OS"], incremental=False)

    source = svc.issue_repo.get_by_field("jira_issue_id", "200")
    links = db_session.query(IssueLink).filter(IssueLink.source_issue_id == source.id).all()
    assert len(links) == 1


@pytest.mark.asyncio
async def test_sync_issues_sets_jira_created_at(db_session):
    """ВАЖНО 3: дата создания задачи в Jira сохраняется отдельно от created_at строки БД."""
    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()

    schema = _issue_schema("300", "OS-300", "p-1", created="2026-07-20T09:00:00.000+0300")

    mock_jira = MagicMock()

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        yield schema

    mock_jira.iter_issues = fake_iter_issues

    svc = SyncService(db_session, mock_jira)
    await svc.sync_issues(project_keys=["OS"], incremental=False)

    issue = svc.issue_repo.get_by_field("jira_issue_id", "300")
    # sync_service._parse_jira_datetime приводит к naive UTC: 09:00 +03:00 → 06:00.
    assert issue.jira_created_at.hour == 6
