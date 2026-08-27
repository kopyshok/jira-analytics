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


def test_whole_mode_excludes_child(client, db_session):
    """RFA целиком — дочерний Эпик отдельным кандидатом не идёт.

    Регресс: часы дочки уже сидят в родительской RFA, поэтому пара
    «RFA + её Эпик» в одном сценарии считала часы дважды.
    """
    _seed_rfa_with_child(db_session)
    sid = _create_scenario(client)
    ids = _alloc_item_ids(client, sid)
    assert "bi-rfa" in ids, "сама RFA остаётся кандидатом"
    assert "bi-epic" not in ids, "дочерний Эпик в режиме whole — не кандидат"


def test_whole_mode_drops_existing_child_allocation(client, db_session):
    """Уже добавленная дочка вычищается из черновика при возврате в whole."""
    _seed_rfa_with_child(db_session)
    r = client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "by_epics"})
    assert r.status_code == 200, r.text
    sid = _create_scenario(client)
    assert "bi-epic" in _alloc_item_ids(client, sid)

    r = client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "whole"})
    assert r.status_code == 200, r.text
    ids = _alloc_item_ids(client, sid)
    assert "bi-epic" not in ids
    assert "bi-rfa" in ids


def _make_multi_team(db, teams):
    """Родителя делают несколько команд — признак мультикомандности."""
    import json as _json
    parent = db.query(Issue).filter_by(id="i-rfa").one()
    parent.team = teams[0]
    parent.participating_teams = _json.dumps(teams, ensure_ascii=False)
    db.commit()


def test_multi_team_parent_is_not_candidate(client, db_session):
    """Мультикомандную RFA целиком планировать нельзя — идут её Эпики."""
    _seed_rfa_with_child(db_session)
    _make_multi_team(db_session, ["Команда А", "Команда Б"])

    sid = _create_scenario(client)
    ids = _alloc_item_ids(client, sid)
    assert "bi-rfa" not in ids, "мультикомандная RFA — контекст, не кандидат"
    assert "bi-epic" in ids, "дочерний Эпик остаётся кандидатом"


def test_single_participant_other_than_product_team_is_multi(client, db_session):
    """Работает одна команда, но не та, что владеет продуктом — тоже группа."""
    _seed_rfa_with_child(db_session)
    import json as _json
    parent = db_session.query(Issue).filter_by(id="i-rfa").one()
    parent.team = "Команда А"
    parent.participating_teams = _json.dumps(["Команда Б"], ensure_ascii=False)
    db_session.commit()

    sid = _create_scenario(client)
    assert "bi-rfa" not in _alloc_item_ids(client, sid)


def test_multi_team_mode_switch_rejected(client, db_session):
    """Переключить мультикомандную RFA обратно в «целиком» нельзя."""
    _seed_rfa_with_child(db_session)
    _make_multi_team(db_session, ["Команда А", "Команда Б"])

    r = client.patch("/api/v1/backlog/bi-rfa/planning-mode", json={"mode": "whole"})
    assert r.status_code == 409, r.text
    r = client.patch("/api/v1/backlog/bi-rfa/included", json={"included": True})
    assert r.status_code == 409, r.text


def test_multi_team_lock_can_be_switched_off(client, db_session):
    """Блокировку можно выключить в настройках — тогда режим решает PM."""
    from app.models import AppSetting
    _seed_rfa_with_child(db_session)
    _make_multi_team(db_session, ["Команда А", "Команда Б"])
    db_session.add(AppSetting(key="planning_multi_team_by_epics", value="false"))
    db_session.commit()

    sid = _create_scenario(client)
    ids = _alloc_item_ids(client, sid)
    assert "bi-rfa" in ids, "блокировка выключена — RFA снова кандидат"
    assert "bi-epic" not in ids, "режим whole снова прячет дочку"


def test_multi_team_flag_exposed_in_backlog(client, db_session):
    """Список бэклога отдаёт признак мультикомандности и состав команд."""
    _seed_rfa_with_child(db_session)
    _make_multi_team(db_session, ["Команда А", "Команда Б"])

    r = client.get("/api/v1/backlog?view=active")
    assert r.status_code == 200, r.text
    rows = {i["id"]: i for i in r.json()}
    parent = rows["bi-rfa"]
    assert parent["is_multi_team"] is True
    assert parent["planning_mode_locked"] is True
    assert parent["participating_teams"] == ["Команда А", "Команда Б"]


def test_parent_context_when_parent_hidden_by_team_filter(client, db_session):
    """Родитель чужой команды не в списке — отдаём его как контекст строки."""
    _seed_rfa_with_child(db_session)
    parent = db_session.query(Issue).filter_by(id="i-rfa").one()
    child = db_session.query(Issue).filter_by(id="i-epic").one()
    parent.team = "Команда А"
    child.team = "Команда Б"
    db_session.commit()

    r = client.get("/api/v1/backlog", params={"view": "active", "teams": "Команда Б"})
    assert r.status_code == 200, r.text
    rows = {i["id"]: i for i in r.json()}
    assert "bi-rfa" not in rows, "родитель чужой команды в список не попадает"
    ctx = rows["bi-epic"]["parent_context"]
    assert ctx is not None and ctx["key"] == "RFA-1"
    assert ctx["team"] == "Команда А"
