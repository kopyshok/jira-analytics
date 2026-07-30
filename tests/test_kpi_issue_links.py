"""Связи задач сохраняются и позволяют найти автора связанной задачи."""
from app.models.issue_link import IssueLink
from app.models.project import Project


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
