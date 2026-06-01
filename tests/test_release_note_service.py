"""Тесты ReleaseNoteService."""
from sqlalchemy.orm import Session

from app.models.release_note import ReleaseNote
from app.models.user import User, UserRole
from app.services.release_note_service import ReleaseNoteService


def _make_note(db, **kwargs):
    defaults = dict(
        note_type="improvement",
        section="general",
        title="Test note",
        description="Test description",
    )
    defaults.update(kwargs)
    svc = ReleaseNoteService(db)
    return svc.create_draft(**defaults)


def test_create_draft_no_version(db_session: Session):
    note = _make_note(db_session)
    assert note.version is None
    assert note.note_type == "improvement"


def test_invalid_note_type_rejected(db_session: Session):
    svc = ReleaseNoteService(db_session)
    try:
        svc.create_draft(
            note_type="wat", section="general", title="x", description="y"
        )
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid note_type")


def test_publish_drafts_assigns_version(db_session: Session):
    _make_note(db_session)
    _make_note(db_session, note_type="new")
    svc = ReleaseNoteService(db_session)
    n = svc.publish_drafts("v1.2.0")
    assert n == 2
    notes = db_session.query(ReleaseNote).all()
    assert all(note.version == "v1.2.0" for note in notes)


def test_publish_drafts_zero_when_none(db_session: Session):
    svc = ReleaseNoteService(db_session)
    assert svc.publish_drafts("v1.2.0") == 0


def test_versions_listing_excludes_drafts(db_session: Session):
    _make_note(db_session)
    n = _make_note(db_session)
    n.version = "v1.0.0"
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    versions = svc.list_published_versions()
    assert versions == ["v1.0.0"]


def test_mark_user_seen_updates_field(db_session: Session):
    user = User(
        email="u@x", password_hash="x", display_name="U", role=UserRole.manager
    )
    db_session.add(user)
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    svc.mark_user_seen(user, "v1.2.0")
    assert user.last_seen_release_version == "v1.2.0"


def test_unread_for_user_returns_versions_after(db_session: Session):
    for v in ["v1.0.0", "v1.1.0", "v1.2.0"]:
        n = _make_note(db_session)
        n.version = v
        db_session.commit()
    user = User(
        email="u@x", password_hash="x", display_name="U",
        role=UserRole.manager, last_seen_release_version="v1.0.0",
    )
    db_session.add(user)
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    unread = svc.unread_versions_for(user)
    assert unread == ["v1.1.0", "v1.2.0"]


def test_unread_for_user_skips_hidden(db_session: Session):
    n = _make_note(db_session)
    n.version = "v1.1.0"
    n.is_hidden = True
    db_session.commit()
    user = User(
        email="u@x", password_hash="x", display_name="U",
        role=UserRole.manager, last_seen_release_version="v1.0.0",
    )
    db_session.add(user)
    db_session.commit()
    svc = ReleaseNoteService(db_session)
    assert svc.unread_versions_for(user) == []


def test_publish_drafts_rejects_bad_version(db_session: Session):
    svc = ReleaseNoteService(db_session)
    _make_note(db_session)
    try:
        svc.publish_drafts("v1.2.0-rc1")
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-strict version")
