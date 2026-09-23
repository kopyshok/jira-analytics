"""Блокировку «В план» считает сервер — по всему бэклогу, а не по списку.

Список с фильтром команды не видит дочерних Эпиков чужой команды, а включить
мультикомандную RFA нельзя, пока у неё есть хоть один не архивный ребёнок где
угодно в бэклоге. Признак строки и отказ при включении — одно правило.
"""
import json
from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.main import app
from app.models import AppSetting, BacklogItem, Issue, Project

TEAM_A = "Команда А"
TEAM_B = "Команда Б"


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _rfa(db, n: int, *, participating: Optional[list[str]], child: Optional[str]) -> str:
    """RFA команды А и, по желанию, её дочерний Эпик команды Б.

    ``child``: None — без детей; "active" — Эпик в бэклоге; "archived" — Эпик
    в архиве бэклога. Возвращает id элемента бэклога RFA.
    """
    if db.get(Project, "p1") is None:
        db.add(Project(id="p1", key="PRJ", jira_project_id="jp1", name="Project"))
        db.flush()
    db.add(Issue(
        id=f"i-rfa{n}", key=f"RFA-{n}", jira_issue_id=f"j-rfa{n}", summary=f"RFA {n}",
        issue_type="RFA", status="Open", project_id="p1", category="initiatives_rfa",
        team=TEAM_A,
        participating_teams=json.dumps(participating, ensure_ascii=False) if participating else None,
    ))
    db.flush()
    db.add(BacklogItem(id=f"bi-rfa{n}", issue_id=f"i-rfa{n}", title=f"RFA {n}", priority=n))
    if child is not None:
        db.add(Issue(
            id=f"i-epic{n}", key=f"EPIC-{n}", jira_issue_id=f"j-epic{n}", summary=f"Эпик {n}",
            issue_type="Epic", status="Open", project_id="p1", parent_id=f"i-rfa{n}",
            category="initiatives_rfa", team=TEAM_B,
        ))
        db.flush()
        db.add(BacklogItem(
            id=f"bi-epic{n}", issue_id=f"i-epic{n}", title=f"Эпик {n}", priority=n,
            archived_at=datetime(2026, 1, 1) if child == "archived" else None,
        ))
    db.commit()
    return f"bi-rfa{n}"


def _row(client, item_id: str, **params) -> dict:
    r = client.get("/api/v1/backlog", params={"view": "active", **params})
    assert r.status_code == 200, r.text
    return {row["id"]: row for row in r.json()}[item_id]


def _include(client, item_id: str, included: bool):
    return client.patch(f"/api/v1/backlog/{item_id}/included", json={"included": included})


def test_lock_visible_when_team_filter_hides_children(client, testclient_db_session):
    """Эпик чужой команды не в списке — блокировка всё равно видна в строке."""
    item_id = _rfa(testclient_db_session, 1, participating=[TEAM_A, TEAM_B], child="active")

    row = _row(client, item_id, teams=TEAM_A)
    assert row["has_children_in_backlog"] is False, "дочка чужой команды в список не попала"
    assert row["include_locked"] is True

    r = _include(client, item_id, True)
    assert r.status_code == 409, r.text
    # Блокировка только на включение: выключить можно.
    assert _include(client, item_id, False).status_code == 200


@pytest.mark.parametrize(
    ("participating", "child", "lock_off", "locked"),
    [
        ([TEAM_A, TEAM_B], "active", False, True),
        ([TEAM_A, TEAM_B], None, False, False),
        ([TEAM_A, TEAM_B], "archived", False, False),
        (None, "active", False, False),
        ([TEAM_A, TEAM_B], "active", True, False),
    ],
    ids=["multi-team-with-child", "no-children", "only-archived-child", "single-team", "lock-off"],
)
def test_include_rejected_iff_row_locked(
    client, testclient_db_session, participating, child, lock_off, locked,
):
    db = testclient_db_session
    item_id = _rfa(db, 1, participating=participating, child=child)
    if lock_off:
        db.add(AppSetting(key="planning_multi_team_by_epics", value="false"))
        db.commit()

    for params in ({"teams": TEAM_A}, {}):
        assert _row(client, item_id, **params)["include_locked"] is locked

    r = _include(client, item_id, True)
    assert r.status_code == (409 if locked else 200), r.text


def test_child_row_carries_lock(client, testclient_db_session):
    """Дочерняя строка тоже несёт признак: мультикомандный Эпик со своим ребёнком."""
    db = testclient_db_session
    _rfa(db, 1, participating=None, child="active")
    db.get(Issue, "i-epic1").participating_teams = json.dumps([TEAM_A, TEAM_B], ensure_ascii=False)
    db.add(Issue(
        id="i-sub", key="EPIC-9", jira_issue_id="j-sub", summary="Под-эпик",
        issue_type="Epic", status="Open", project_id="p1", parent_id="i-epic1",
        category="initiatives_rfa", team=TEAM_B,
    ))
    db.flush()
    db.add(BacklogItem(id="bi-sub", issue_id="i-sub", title="Под-эпик", priority=9))
    db.commit()

    root = _row(client, "bi-rfa1")
    assert root["include_locked"] is False
    kids = {c["id"]: c for c in root["children"]}
    assert kids["bi-epic1"]["include_locked"] is True
    assert _include(client, "bi-epic1", True).status_code == 409


def test_single_item_responses_carry_lock(client, testclient_db_session):
    item_id = _rfa(testclient_db_session, 1, participating=[TEAM_A, TEAM_B], child="active")

    r = client.get(f"/api/v1/backlog/{item_id}")
    assert r.status_code == 200, r.text
    assert r.json()["include_locked"] is True

    r = client.patch(f"/api/v1/backlog/{item_id}", json={"priority": 3})
    assert r.status_code == 200, r.text
    assert r.json()["include_locked"] is True


def _list_query_count(client, engine) -> int:
    count = 0

    def _on_execute(*_args, **_kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        r = client.get("/api/v1/backlog", params={"view": "active", "teams": TEAM_A})
        assert r.status_code == 200, r.text
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)
    return count


def test_lock_computed_without_per_row_queries(client, testclient_db_session):
    """Число запросов списка не растёт с числом заблокированных RFA."""
    db = testclient_db_session
    engine = db.get_bind()
    _rfa(db, 1, participating=[TEAM_A, TEAM_B], child="active")
    _list_query_count(client, engine)  # прогрев кэшей
    one = _list_query_count(client, engine)
    for n in (2, 3, 4):
        _rfa(db, n, participating=[TEAM_A, TEAM_B], child="active")
    rows = client.get("/api/v1/backlog", params={"view": "active", "teams": TEAM_A}).json()
    assert sum(row["include_locked"] for row in rows) == 4
    assert _list_query_count(client, engine) == one
