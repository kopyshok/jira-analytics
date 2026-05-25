"""Тесты FeedbackService."""
import json

import pytest
from sqlalchemy.orm import Session

from app.models.feedback import FeedbackKind
from app.models.user import User, UserRole
from app.schemas.feedback import AttachmentRef, BugCreate, FeedbackContext, IdeaCreate
from app.services.feedback_service import FeedbackService


@pytest.fixture
def author(db_session: Session) -> User:
    u = User(
        email="bob@example.com",
        password_hash="x",
        display_name="Bob",
        role=UserRole.manager,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def test_create_bug_persists_all_fields(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    payload = BugCreate(
        title="UI crash on Gantt",
        body="Page freezes when scrolling",
        page_url="/resource-planning",
        steps_to_reproduce="1. open\n2. scroll right",
        expected="smooth scroll",
        actual="freeze",
        context=FeedbackContext(
            user_agent="Chrome 130",
            active_team="ITGRI",
            console_errors=[{"ts": "2026-05-25T10:00:00Z", "message": "TypeError"}],
        ),
        attachments=[AttachmentRef(filename="s.png", mime="image/png", size=12, path="x.png")],
    )
    item = svc.create_bug(db_session, author=author, payload=payload)
    assert item.kind == FeedbackKind.bug
    assert item.author_id == author.id
    assert item.read_at is None
    ctx = json.loads(item.context_json)
    assert ctx["active_team"] == "ITGRI"
    atts = json.loads(item.attachments_json)
    assert atts[0]["filename"] == "s.png"


def test_create_idea_minimal_fields(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    payload = IdeaCreate(
        title="Add CSV export",
        body="Would be useful on /analytics",
        page_url="/analytics",
    )
    item = svc.create_idea(db_session, author=author, payload=payload)
    assert item.kind == FeedbackKind.idea
    assert item.steps_to_reproduce is None
    assert item.context_json is None


def test_list_admin_filter_unread(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    a = svc.create_bug(db_session, author=author, payload=BugCreate(title="A", body="x"))
    b = svc.create_bug(db_session, author=author, payload=BugCreate(title="B", body="y"))
    svc.mark_read(db_session, ids=[a.id], reader_id=author.id)

    unread = svc.list_for_admin(db_session, kind=FeedbackKind.bug, filter_mode="unread")
    assert {x.id for x in unread} == {b.id}

    all_items = svc.list_for_admin(db_session, kind=FeedbackKind.bug, filter_mode="all")
    assert {x.id for x in all_items} == {a.id, b.id}


def test_list_user_scope_mine_only_own_bugs(db_session: Session, author: User) -> None:
    other = User(
        email="alice@example.com", password_hash="x", display_name="Alice", role=UserRole.manager,
    )
    db_session.add(other)
    db_session.commit()
    svc = FeedbackService()
    own = svc.create_bug(db_session, author=author, payload=BugCreate(title="Own", body="b"))
    svc.create_bug(db_session, author=other, payload=BugCreate(title="Other", body="b"))

    mine = svc.list_for_user(
        db_session, author_id=author.id, kind=FeedbackKind.bug, scope="mine"
    )
    assert {x.id for x in mine} == {own.id}


def test_list_user_scope_all_ideas_visible(db_session: Session, author: User) -> None:
    other = User(
        email="alice@example.com", password_hash="x", display_name="Alice", role=UserRole.manager,
    )
    db_session.add(other)
    db_session.commit()
    svc = FeedbackService()
    own = svc.create_idea(db_session, author=author, payload=IdeaCreate(title="A", body="b"))
    foreign = svc.create_idea(db_session, author=other, payload=IdeaCreate(title="B", body="b"))

    feed = svc.list_for_user(
        db_session, author_id=author.id, kind=FeedbackKind.idea, scope="all"
    )
    assert {x.id for x in feed} == {own.id, foreign.id}


def test_mark_unread_clears_read_at(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    item = svc.create_bug(db_session, author=author, payload=BugCreate(title="T", body="b"))
    svc.mark_read(db_session, ids=[item.id], reader_id=author.id)
    db_session.refresh(item)
    assert item.read_at is not None
    svc.mark_unread(db_session, ids=[item.id])
    db_session.refresh(item)
    assert item.read_at is None
    assert item.read_by is None
