"""Плашка «в работе у K из N» в строках сценария.

Строка эпика мультикомандной RFA показывает, сколько команд RFA уже взяли
работу, и статус своей команды. Считается одним проходом на все строки.
"""
import json
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
    issue_type: str = "Эпик",
) -> None:
    db.add(Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}", summary=key, issue_type=issue_type,
        status="Backlog", project_id="p-os", parent_id=f"i-{parent}" if parent else None,
        category=category, team=team,
        participating_teams=json.dumps(participating, ensure_ascii=False) if participating else None,
    ))
    db.flush()
    db.add(BacklogItem(id=f"bi-{key}", issue_id=f"i-{key}", title=key, priority=1))
    db.flush()


def _alloc(db, sid: str, key: str, included: bool) -> None:
    db.add(ScenarioAllocation(
        scenario_id=sid, backlog_item_id=f"bi-{key}", included_flag=included, planned_hours=0,
    ))
    db.flush()


def _seed_rfa(db, n: int) -> None:
    """RFA команды А на А и Б: эпик А утверждён, эпик Б в черновике Б не включён."""
    _add(db, f"RFA-{n}", team=TEAM_A, participating=[TEAM_A, TEAM_B], issue_type="Инициатива")
    _add(db, f"OS-{n}A", team=TEAM_A, parent=f"RFA-{n}", category="quarterly_tasks")
    _add(db, f"OS-{n}B", team=TEAM_B, parent=f"RFA-{n}")
    _alloc(db, "s-mt-a", f"OS-{n}A", True)
    _alloc(db, "s-mt-b", f"OS-{n}B", False)


def _seed(db) -> None:
    db.add(Project(id="p-os", key="OS", jira_project_id="jp-os", name="OS"))
    db.add_all([
        PlanningScenario(id="s-mt-a", name="План А", year=2099, quarter="Q1",
                         status="approved", team=TEAM_A),
        PlanningScenario(id="s-mt-b", name="Черновик Б", year=2099, quarter="Q1",
                         status="draft", team=TEAM_B),
    ])
    db.flush()
    _seed_rfa(db, 1)
    _add(db, "OS-PLAIN", team=TEAM_B, issue_type="Задача")
    _alloc(db, "s-mt-b", "OS-PLAIN", False)
    db.commit()


def _rows(client) -> dict[str, dict]:
    r = client.get("/api/v1/planning/scenarios/s-mt-b/allocations")
    assert r.status_code == 200, r.text
    return {row["jira_key"]: row for row in r.json()}


def test_epic_row_shows_progress(client, testclient_db_session):
    _seed(testclient_db_session)

    rows = _rows(client)

    progress = rows["OS-1B"]["multi_team_progress"]
    assert (progress["taken"], progress["total"]) == (1, 2)
    assert (progress["own_team"], progress["own_status"]) == (TEAM_B, "not_taken")
    assert progress["teams"][0] == {
        "team": TEAM_A, "status": "taken",
        "scenarios": [{"id": "s-mt-a", "name": "План А", "quarter_label": "1 кв. 2099"}],
    }
    assert rows["OS-PLAIN"]["multi_team_progress"] is None


def _query_count(client, engine) -> int:
    count = 0

    def _on_execute(*_args, **_kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        _rows(client)
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)
    return count


def test_query_count_does_not_grow_with_rows(client, testclient_db_session):
    db = testclient_db_session
    engine = db.get_bind()
    _seed(db)
    _rows(client)  # прогрев: самолечение черновика и кэши
    one = _query_count(client, engine)
    for n in range(2, 6):
        _seed_rfa(db, n)
    db.commit()
    rows = _rows(client)
    assert [rows[f"OS-{n}B"]["multi_team_progress"]["taken"] for n in range(2, 6)] == [1] * 4
    assert _query_count(client, engine) == one
