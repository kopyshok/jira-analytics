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


def test_list_user_scope_all_bugs_returns_all_at_service_level(
    db_session: Session, author: User
) -> None:
    other = User(
        email="charlie@example.com", password_hash="x", display_name="Charlie", role=UserRole.manager,
    )
    db_session.add(other)
    db_session.commit()
    svc = FeedbackService()
    own = svc.create_bug(db_session, author=author, payload=BugCreate(title="O", body="b"))
    foreign = svc.create_bug(db_session, author=other, payload=BugCreate(title="F", body="b"))
    result = svc.list_for_user(
        db_session, author_id=author.id, kind=FeedbackKind.bug, scope="all"
    )
    assert {x.id for x in result} == {own.id, foreign.id}


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


def test_export_markdown_bug_contains_all_sections(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    item = svc.create_bug(
        db_session,
        author=author,
        payload=BugCreate(
            title="Crash",
            body="freezes",
            steps_to_reproduce="1. click",
            expected="ok",
            actual="crash",
            page_url="/x",
            context=FeedbackContext(active_team="ITGRI", user_agent="Chrome"),
        ),
    )
    md = svc.export_markdown(
        db_session, kind=FeedbackKind.bug, ids=[item.id], only_unread=False, mark_after=False
    )
    assert "## #1 — Crash" in md
    assert "Шаги воспроизведения" in md
    assert "ITGRI" in md
    assert "Chrome" in md


def test_export_markdown_mark_after_marks_unread(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    a = svc.create_bug(db_session, author=author, payload=BugCreate(title="A", body="b"))
    b = svc.create_bug(db_session, author=author, payload=BugCreate(title="B", body="b"))
    svc.export_markdown(
        db_session,
        kind=FeedbackKind.bug,
        ids=None,
        only_unread=True,
        mark_after=True,
        reader_id=author.id,
    )
    db_session.refresh(a)
    db_session.refresh(b)
    assert a.read_at is not None
    assert b.read_at is not None


def test_export_markdown_idea_format(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    item = svc.create_idea(
        db_session, author=author, payload=IdeaCreate(title="CSV", body="useful")
    )
    md = svc.export_markdown(
        db_session, kind=FeedbackKind.idea, ids=[item.id], only_unread=False, mark_after=False
    )
    assert "# Идеи — выгрузка" in md
    assert "CSV" in md
    assert "Шаги воспроизведения" not in md  # idea md skips bug-only sections


def test_export_mark_after_requires_reader_id(db_session: Session, author: User) -> None:
    svc = FeedbackService()
    svc.create_bug(db_session, author=author, payload=BugCreate(title="x", body="b"))
    with pytest.raises(ValueError, match="reader_id required"):
        svc.export_markdown(
            db_session,
            kind=FeedbackKind.bug,
            ids=None,
            only_unread=True,
            mark_after=True,
            reader_id=None,
        )


def test_save_attachment_returns_ref(tmp_path) -> None:
    storage = tmp_path / "atts"
    svc = FeedbackService(attachments_dir=str(storage))
    ref = svc.save_attachment(filename="screenshot.png", mime="image/png", data=b"\x89PNG...")
    assert ref.filename == "screenshot.png"
    assert ref.mime == "image/png"
    assert ref.size == len(b"\x89PNG...")
    assert (storage / ref.path).exists()


def test_save_attachment_rejects_bad_mime(tmp_path) -> None:
    svc = FeedbackService(attachments_dir=str(tmp_path))
    with pytest.raises(ValueError):
        svc.save_attachment(filename="evil.exe", mime="application/x-msdownload", data=b"X")


def test_save_attachment_rejects_oversize(tmp_path) -> None:
    svc = FeedbackService(attachments_dir=str(tmp_path))
    with pytest.raises(ValueError):
        svc.save_attachment(
            filename="big.png", mime="image/png", data=b"X" * (5 * 1024 * 1024 + 1)
        )
