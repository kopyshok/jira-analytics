"""Бэклог: аналитик и разработчик строки правятся; один человек — одна роль."""
import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import BacklogItem
from tests.services.xteam_factory import make_employee


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def idea(db_session):
    it = BacklogItem(title="Идея", team="B")
    db_session.add(it)
    db_session.commit()
    return it


def _patch(client, item_id, body):
    return client.patch(f"/api/v1/backlog/{item_id}", json=body)


def test_patch_developer_and_assignee(client, db_session, idea):
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    dev = make_employee(db_session, "Разработчик", "B")
    db_session.commit()

    r = _patch(client, idea.id, {"assignee_employee_id": an.id, "developer_employee_id": dev.id})

    assert r.status_code == 200, r.text
    assert r.json()["assignee_employee_id"] == an.id
    assert r.json()["developer_employee_id"] == dev.id
    assert r.json()["developer_display_name"] == "Разработчик"
    db_session.expire_all()
    item = db_session.get(BacklogItem, idea.id)
    assert item.assignee_employee_id == an.id
    assert item.developer_employee_id == dev.id


def test_patch_same_person_is_422(client, db_session, idea):
    dev = make_employee(db_session, "Разработчик", "B")
    db_session.commit()
    assert _patch(client, idea.id, {"developer_employee_id": dev.id}).status_code == 200

    r = _patch(client, idea.id, {"assignee_employee_id": dev.id})

    assert r.status_code == 422, r.text


def test_patch_unknown_developer_is_404(client, idea):
    assert _patch(client, idea.id, {"developer_employee_id": "nope"}).status_code == 404
