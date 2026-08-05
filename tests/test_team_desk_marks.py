"""Отметка «просмотрено» и её сгорание при изменении причины."""
import uuid

import pytest

from app.models import Issue, Project, TeamDeskMark
from app.services.team_desk.marks import active_marks, mark_reviewed, unmark


@pytest.fixture()
def issue(db_session):
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id=str(uuid.uuid4()),
        key=f"OS{uuid.uuid4().hex[:4]}",
        name="OS",
    )
    db_session.add(project)
    db_session.flush()
    row = Issue(
        id=str(uuid.uuid4()),
        jira_issue_id=str(uuid.uuid4()),
        key="OS-1",
        summary="Задача",
        issue_type="Задача",
        status="В РАБОТЕ",
        project_id=project.id,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_mark_stores_author_and_comment(db_session, issue, seed_user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment="ждём заказчика", user_id=seed_user.id)

    marks = active_marks(db_session, [issue.id], {("stale", issue.id): "В РАБОТЕ"})
    assert (issue.id, "stale") in marks
    assert marks[(issue.id, "stale")].comment == "ждём заказчика"
    assert marks[(issue.id, "stale")].created_by_user_id == seed_user.id


def test_mark_burns_when_signature_changes(db_session, issue, seed_user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=seed_user.id)

    # задача уехала в другой статус — отсчёт дней начался заново
    marks = active_marks(db_session, [issue.id], {("stale", issue.id): "КОД-РЕВЬЮ"})
    assert marks == {}
    assert db_session.query(TeamDeskMark).count() == 0


def test_mark_is_per_flag(db_session, issue, seed_user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=seed_user.id)

    current = {("stale", issue.id): "В РАБОТЕ", ("over", issue.id): "6:9"}
    marks = active_marks(db_session, [issue.id], current)
    assert (issue.id, "stale") in marks
    assert (issue.id, "over") not in marks


def test_second_mark_replaces_first(db_session, issue, seed_user):
    mark_reviewed(db_session, issue.id, "over", signature="6:9",
                  comment="a", user_id=seed_user.id)
    mark_reviewed(db_session, issue.id, "over", signature="6:12",
                  comment="b", user_id=seed_user.id)

    marks = active_marks(db_session, [issue.id], {("over", issue.id): "6:12"})
    assert marks[(issue.id, "over")].comment == "b"
    assert db_session.query(TeamDeskMark).count() == 1


def test_unmark_removes(db_session, issue, seed_user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=seed_user.id)
    unmark(db_session, issue.id, "stale")

    assert active_marks(db_session, [issue.id], {("stale", issue.id): "В РАБОТЕ"}) == {}
