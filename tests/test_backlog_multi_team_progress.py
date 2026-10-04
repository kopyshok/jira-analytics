"""Плашка «в работе у K из N» на «Целевых задачах».

У строки мультикомандной RFA и у строк её эпиков — одни и те же K и N и статус
своей команды строки. Считается одним проходом на весь список.
"""
import json
from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.main import app
from app.models import BacklogItem, Issue, PlanningScenario, Project, ScenarioAllocation

TEAM_A = "Команда А"
TEAM_B = "Команда Б"


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _add(
    db, key: str, *, team: str, parent: Optional[str] = None,
    participating: Optional[list[str]] = None, category: str = "initiatives_rfa",
    issue_type: str = "Эпик", archived: bool = False,
) -> None:
    db.add(Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}", summary=key, issue_type=issue_type,
        status="Backlog", project_id="p-os", parent_id=f"i-{parent}" if parent else None,
        category=category, team=team,
        participating_teams=json.dumps(participating, ensure_ascii=False) if participating else None,
    ))
    db.flush()
    db.add(BacklogItem(
        id=f"bi-{key}", issue_id=f"i-{key}", title=key, priority=1,
        archived_at=datetime(2026, 1, 1) if archived else None,
    ))
    db.flush()


def _seed_rfa(db, n: int = 1) -> None:
    """RFA команды А на А и Б: эпик А утверждён в будущем квартале, эпик Б — нет."""
    _add(db, f"RFA-{n}", team=TEAM_A, participating=[TEAM_A, TEAM_B], issue_type="Инициатива")
    _add(db, f"OS-{n}A", team=TEAM_A, parent=f"RFA-{n}", category="quarterly_tasks")
    _add(db, f"OS-{n}B", team=TEAM_B, parent=f"RFA-{n}")
    db.add(ScenarioAllocation(
        scenario_id="s-a", backlog_item_id=f"bi-OS-{n}A", included_flag=True, planned_hours=0,
    ))
    db.flush()


def _seed(db) -> None:
    db.add(Project(id="p-os", key="OS", jira_project_id="jp-os", name="OS"))
    db.add(PlanningScenario(
        id="s-a", name="План А", year=2099, quarter="Q1", status="approved", team=TEAM_A,
    ))
    db.flush()
    _seed_rfa(db)
    _add(db, "OS-PLAIN", team=TEAM_A, issue_type="Задача")
    _add(db, "RFA-OLD", team=TEAM_A, participating=[TEAM_A, TEAM_B], issue_type="Инициатива",
         archived=True)
    db.commit()


def _rows(client, **params) -> dict[str, dict]:
    """Строки списка по ключу Jira — и корни, и дочерние строки."""
    r = client.get("/api/v1/backlog", params=params)
    assert r.status_code == 200, r.text
    out: dict[str, dict] = {}
    for row in r.json():
        out[row["jira_key"]] = row
        for child in row.get("children") or []:
            out[child["key"]] = child
    return out


def _short(progress: Optional[dict]) -> Optional[tuple]:
    if progress is None:
        return None
    return progress["taken"], progress["total"], progress["own_team"], progress["own_status"]


def test_rfa_row_and_child_epic_row(client, testclient_db_session):
    _seed(testclient_db_session)

    rows = _rows(client, view="active")

    rfa = rows["RFA-1"]["multi_team_progress"]
    assert _short(rfa) == (1, 2, TEAM_A, "taken")
    assert [(t["team"], t["status"]) for t in rfa["teams"]] == [
        (TEAM_A, "taken"), (TEAM_B, "not_taken"),
    ]
    assert rfa["teams"][0]["scenarios"] == [
        {"id": "s-a", "name": "План А", "quarter_label": "1 кв. 2099"},
    ]
    assert _short(rows["OS-1B"]["multi_team_progress"]) == (1, 2, TEAM_B, "not_taken")
    assert rows["OS-PLAIN"]["multi_team_progress"] is None


def test_epic_row_with_parent_outside_the_list(client, testclient_db_session):
    """Фильтр своей команды: RFA чужой команды в список не попала, эпик идёт корнем."""
    _seed(testclient_db_session)

    assert _short(_rows(client, view="active", teams=TEAM_B)["OS-1B"]["multi_team_progress"]) == (
        1, 2, TEAM_B, "not_taken",
    )
    assert _short(
        _rows(client, view="quarterly", teams=TEAM_A)["OS-1A"]["multi_team_progress"]
    ) == (1, 2, TEAM_A, "taken")


def test_archive_has_no_progress(client, testclient_db_session):
    _seed(testclient_db_session)

    assert _rows(client, view="archived")["RFA-OLD"]["multi_team_progress"] is None


def _list_query_count(client, engine) -> int:
    count = 0

    def _on_execute(*_args, **_kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        r = client.get("/api/v1/backlog", params={"view": "active"})
        assert r.status_code == 200, r.text
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)
    return count


def test_query_count_does_not_grow_with_multi_team_rfas(client, testclient_db_session):
    db = testclient_db_session
    engine = db.get_bind()
    _seed(db)
    _list_query_count(client, engine)  # прогрев кэшей
    one = _list_query_count(client, engine)
    for n in range(2, 6):
        _seed_rfa(db, n)
    db.commit()
    rows = _rows(client, view="active")
    assert [_short(rows[f"RFA-{n}"]["multi_team_progress"])[0] for n in range(2, 6)] == [1] * 4
    assert _list_query_count(client, engine) == one
