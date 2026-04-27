import uuid
import pytest
from sqlalchemy.orm import Session
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


@pytest.fixture
def repo():
    return UserRepository()


def _make(db: Session, email: str, role: UserRole = UserRole.manager) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash=hash_password("secret"),
        display_name="Test",
        role=role,
        is_active=True,
    )
    db.add(u)
    db.commit()
    return u


def test_get_by_email_found(db_session, repo):
    _make(db_session, "a@x.com")
    found = repo.get_by_email(db_session, "a@x.com")
    assert found is not None
    assert found.email == "a@x.com"


def test_get_by_email_not_found(db_session, repo):
    assert repo.get_by_email(db_session, "nobody@x.com") is None


def test_get_by_id(db_session, repo):
    u = _make(db_session, "b@x.com")
    found = repo.get_by_id(db_session, u.id)
    assert found is not None


def test_list_all(db_session, repo):
    _make(db_session, "c@x.com")
    _make(db_session, "d@x.com")
    assert len(repo.list_all(db_session)) >= 2
