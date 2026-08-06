"""Отметка «просмотрено» и её сгорание при изменении причины."""
import uuid
from datetime import datetime, timedelta

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


def test_reviewed_flag_hidden_when_switch_off(db_session, issue, seed_user):
    """Отмеченный признак не показывается вообще, пока не включён показ."""
    from app.services.team_desk.query import build_overview

    issue.developer_account_id = "acc-1"
    issue.developer_display_name = "Шутов Сергей"
    issue.status_changed_at = datetime.utcnow() - timedelta(days=30)
    db_session.commit()

    before = build_overview(db_session, ["acc-1"], show_reviewed=False)["issues"][0]
    assert "stale" in before["flags"]

    mark_reviewed(db_session, issue.id, "stale", signature=before["signatures"]["stale"],
                  comment="разобрались", user_id=seed_user.id)

    hidden = build_overview(db_session, ["acc-1"], show_reviewed=False)
    assert "stale" not in hidden["issues"][0]["flags"]
    assert hidden["issues"][0]["reviewed"] == []
    assert "stale" not in hidden["flag_counts"]

    shown = build_overview(db_session, ["acc-1"], show_reviewed=True)
    assert "stale" in shown["issues"][0]["flags"]
    assert shown["issues"][0]["reviewed"][0]["comment"] == "разобрались"


def test_unmark_removes(db_session, issue, seed_user):
    mark_reviewed(db_session, issue.id, "stale", signature="В РАБОТЕ",
                  comment=None, user_id=seed_user.id)
    unmark(db_session, issue.id, "stale")

    assert active_marks(db_session, [issue.id], {("stale", issue.id): "В РАБОТЕ"}) == {}
