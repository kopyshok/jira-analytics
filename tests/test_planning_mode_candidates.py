"""Режим планирования группы RFA влияет на состав кандидатов сценария.

«По Эпикам» → RFA-родитель уходит в контекст (исчезает из сценария по
умолчанию), дочерние Эпики остаются кандидатами. Галочка «Включить саму RFA»
(included_in_planning=True) возвращает родителя.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import BacklogItem, Issue, Project, ScenarioAllocation


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _seed_rfa_with_child(db):
    """RFA-родитель + дочерний Эпик в бэклоге (Эпик.parent_id == RFA.id)."""
    p = Project(id="p1", key="PRJ", jira_project_id="jp1", name="Project")
    db.add(p)
    parent = Issue(
        id="i-rfa", key="RFA-1", jira_issue_id="j-rfa", summary="RFA parent",
        issue_type="RFA", status="Open", project_id="p1", category="initiatives_rfa",
    )
    child = Issue(
        id="i-epic", key="EPIC-1", jira_issue_id="j-epic", summary="Child epic",
        issue_type="Epic", status="Open", project_id="p1", parent_id="i-rfa",
        category="initiatives_rfa",
    )
    db.add_all([parent, child])
    bi_parent = BacklogItem(id="bi-rfa", issue_id="i-rfa", title="RFA parent", priority=1)
    bi_child = BacklogItem(id="bi-epic", issue_id="i-epic", title="Child epic", priority=2)
    db.add_all([bi_parent, bi_child])
    db.commit()
    return bi_parent, bi_child


def _create_scenario(client) -> str:
    r = client.post(
        "/api/v1/planning/scenarios",
        json={"name": "Q2", "year": 2026, "quarter": 2},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _alloc_item_ids(client, sid) -> set:
    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    assert r.status_code == 200, r.text
    return {a["backlog_item_id"] for a in r.json()}


def test_whole_mode_keeps_parent_candidate(client, db_session):
    """Дефолтный режим whole — родитель остаётся кандидатом сценария."""
    _seed_rfa_with_child(db_session)
    sid = _create_scenario(client)
    ids = _alloc_item_ids(client, sid)
    assert "bi-rfa" in ids


def test_by_epics_excludes_parent_keeps_child(client, db_session):
    """По Эпикам — родитель уходит из кандидатов, ребёнок остаётся."""
    _seed_rfa_with_child(db_session)
    r = client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "by_epics"})
    assert r.status_code == 200, r.text

    sid = _create_scenario(client)
    ids = _alloc_item_ids(client, sid)
    assert "bi-rfa" not in ids, "RFA-родитель должен стать контекстом"
    assert "bi-epic" in ids, "дочерний Эпик остаётся кандидатом"


def test_by_epics_sets_included_false(client, db_session):
    """Переход в by_epics по умолчанию делает родителя контекстом."""
    _seed_rfa_with_child(db_session)
    r = client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "by_epics"})
    assert r.status_code == 200
    assert r.json()["included_in_planning"] is False
    db_session.expire_all()
    assert db_session.get(BacklogItem, "bi-rfa").included_in_planning is False


def test_by_epics_opt_in_re_includes_parent(client, db_session):
    """Галочка «Включить саму RFA» возвращает родителя в кандидаты."""
    _seed_rfa_with_child(db_session)
    client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "by_epics"})
    r = client.patch("/api/v1/backlog/bi-rfa/included", json={"included": True})
    assert r.status_code == 200

    sid = _create_scenario(client)
    ids = _alloc_item_ids(client, sid)
    assert "bi-rfa" in ids, "после opt-in родитель снова кандидат"
    assert "bi-epic" in ids


def test_patch_reconciles_existing_draft_allocations(client, db_session):
    """Смена режима у существующего черновика немедленно правит allocations."""
    _seed_rfa_with_child(db_session)
    sid = _create_scenario(client)
    # Сценарий создан в режиме whole — у родителя есть allocation.
    db_session.expire_all()
    assert (
        db_session.query(ScenarioAllocation)
        .filter_by(scenario_id=sid, backlog_item_id="bi-rfa")
        .count()
        == 1
    )

    # Переключаем родителя на by_epics → его allocation должна исчезнуть сразу
    # (reconcile в PATCH, до любого GET self-heal).
    client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "by_epics"})
    db_session.expire_all()
    assert (
        db_session.query(ScenarioAllocation)
        .filter_by(scenario_id=sid, backlog_item_id="bi-rfa")
        .count()
        == 0
    )

    # Возврат в whole → allocation восстановлена.
    client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "whole"})
    db_session.expire_all()
    assert (
        db_session.query(ScenarioAllocation)
        .filter_by(scenario_id=sid, backlog_item_id="bi-rfa")
        .count()
        == 1
    )
