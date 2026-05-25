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
            active_team="ACME",
            console_errors=[{"ts": "2026-05-25T10:00:00Z", "message": "TypeError"}],
        ),
        attachments=[AttachmentRef(filename="s.png", mime="image/png", size=12, path="x.png")],
    )
    item = svc.create_bug(db_session, author=author, payload=payload)
    assert item.kind == FeedbackKind.bug
    assert item.author_id == author.id
    assert item.read_at is None
    ctx = json.loads(item.context_json)
    assert ctx["active_team"] == "ACME"
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
