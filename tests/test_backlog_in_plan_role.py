"""Роль переключателя «В план» считает сервер — по всему бэклогу, а не по списку.

Список не видит всей группы RFA: родитель бывает чужой команды (фильтр), на
другой вкладке, утверждён или выполнен, а эпики спрятаны фильтром. Роль «эпик
внутри RFA целиком» совпадает с тем, что отбор кандидатов исключает как детей
родителя «целиком», — при любом фильтре и на любой вкладке.
"""
from datetime import datetime
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.main import app
from app.models import (
    BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation,
)
from app.services.backlog_service import mode_excluded_backlog_ids, mode_group_ids

TEAM_A = "Команда А"
TEAM_B = "Команда Б"
RFA = {"project": "p-rfa", "issue_type": "RFA"}


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _add(
    db, key: str, *, parent: Optional[str] = None, team: str = TEAM_A,
    project: str = "p-os", issue_type: str = "Epic", category: str = "initiatives_rfa",
    status_category: Optional[str] = None, participating: Optional[str] = None,
    mode: str = "whole", included: bool = True, archived: bool = False,
) -> str:
    """Задача и её элемент бэклога ``bi-<key>``."""
    db.add(Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}", summary=key, issue_type=issue_type,
        status="Open", status_category=status_category, project_id=project,
        parent_id=f"i-{parent}" if parent else None, category=category, team=team,
        participating_teams=participating,
    ))
    db.flush()
    db.add(BacklogItem(
        id=f"bi-{key}", issue_id=f"i-{key}", title=key, priority=1,
        planning_mode=mode, included_in_planning=included,
        archived_at=datetime(2026, 1, 1) if archived else None,
    ))
    db.flush()
    return f"bi-{key}"


def _seed(db) -> None:
    db.add_all([
        # Дискавери: эпик проекта RFA внутри RFA — служебный, часы сверх родителя.
        HierarchyRule(priority=5, project_key="RFA", issue_type="Эпик", require_no_parent=False,
                      require_parent=True, is_container=False, is_enabled=True, description="svc"),
        HierarchyRule(priority=10, project_key="RFA", issue_type=None, require_no_parent=False,
                      require_parent=False, is_container=True, is_enabled=True),
        Project(id="p-rfa", key="RFA", jira_project_id="jp-rfa", name="RFA"),
        Project(id="p-os", key="OS", jira_project_id="jp-os", name="OS"),
    ])
    db.flush()
    # Эпик и Дискавери чужой команды: с фильтром их команды идут корнем.
    _add(db, "RFA-1", **RFA)
    _add(db, "OS-1", parent="RFA-1", team=TEAM_B)
    _add(db, "RFA-2", parent="RFA-1", team=TEAM_B, project="p-rfa", issue_type="Эпик",
         included=False)
    # Родитель — квартальная задача на вкладке «Активные», эпик — в «Бэклоге».
    _add(db, "RFA-10", category="quarterly_tasks", **RFA)
    _add(db, "OS-10", parent="RFA-10")
    # Родитель утверждён в сценарии — из «Бэклога» уходит.
    _add(db, "RFA-20", **RFA)
    _add(db, "OS-20", parent="RFA-20")
    # Родитель выполнен — из «Бэклога» уходит, но из бэклога не архивирован.
    _add(db, "RFA-30", status_category="done", **RFA)
    _add(db, "OS-30", parent="RFA-30")
    # Родитель в архиве бэклога — группы нет, эпик сам себе кандидат.
    _add(db, "RFA-40", archived=True, **RFA)
    _add(db, "OS-40", parent="RFA-40")
    # «По эпикам», эпик только чужой команды.
    _add(db, "RFA-50", mode="by_epics", included=False, **RFA)
    _add(db, "OS-50", parent="RFA-50", team=TEAM_B)
    db.add(PlanningScenario(id="s-appr", name="Утверждён", year=2026, quarter="Q3",
                            status="approved", team=TEAM_A))
    db.flush()
    db.add(ScenarioAllocation(scenario_id="s-appr", backlog_item_id="bi-RFA-20",
                              included_flag=True, planned_hours=0, sort_order=1.0))
    db.commit()


def _roles(client, **params) -> dict[str, str]:
    """Роль каждой строки списка — и корней, и дочерних строк."""
    r = client.get("/api/v1/backlog", params=params)
    assert r.status_code == 200, r.text
    roles: dict[str, str] = {}
    for row in r.json():
        roles[row["id"]] = row["in_plan_role"]
        for child in row["children"]:
            roles[child["id"]] = child["in_plan_role"]
    return roles


LISTS = [
    {"view": "active"},
    {"view": "active", "teams": TEAM_A},
    {"view": "active", "teams": TEAM_B},
    {"view": "quarterly"},
    {"view": "quarterly", "teams": TEAM_A},
]


@pytest.mark.parametrize("params", LISTS, ids=lambda p: "-".join(p.values()))
def test_inert_iff_whole_child(client, testclient_db_session, params):
    """«Неактивен» ровно у тех, кого отбор исключает как ребёнка RFA «целиком»."""
    db = testclient_db_session
    _seed(db)
    _, whole_children = mode_group_ids(db)
    excluded = mode_excluded_backlog_ids(db)

    roles = _roles(client, **params)
    assert roles
    for item_id, role in roles.items():
        assert (role == "inert") == (item_id in whole_children), item_id
        if role == "inert":
            assert item_id in excluded, item_id


@pytest.mark.parametrize(
    ("params", "item_id", "role"),
    [
        ({"view": "active", "teams": TEAM_B}, "bi-OS-1", "inert"),
        ({"view": "active"}, "bi-OS-1", "inert"),
        ({"view": "active", "teams": TEAM_B}, "bi-RFA-2", "regular"),
        ({"view": "active"}, "bi-RFA-1", "regular"),
        ({"view": "active"}, "bi-OS-10", "inert"),
        ({"view": "quarterly"}, "bi-RFA-10", "regular"),
        ({"view": "active"}, "bi-OS-20", "inert"),
        ({"view": "active"}, "bi-OS-30", "inert"),
        ({"view": "active"}, "bi-OS-40", "regular"),
        ({"view": "active", "teams": TEAM_A}, "bi-RFA-50", "by_epics"),
        ({"view": "active"}, "bi-RFA-50", "by_epics"),
        ({"view": "active", "teams": TEAM_B}, "bi-OS-50", "regular"),
    ],
    ids=[
        "parent-hidden-by-team-filter", "child-row", "discovery-on-top-of-parent",
        "whole-parent", "parent-on-other-tab", "quarterly-parent", "approved-parent",
        "done-parent", "archived-parent-no-group", "by-epics-children-hidden",
        "by-epics-children-shown", "by-epics-child",
    ],
)
def test_role_independent_of_list(client, testclient_db_session, params, item_id, role):
    _seed(testclient_db_session)
    assert _roles(client, **params)[item_id] == role


def test_locked_and_nested_roles(client, testclient_db_session):
    """Мультикомандная RFA с эпиками — «только по эпикам». Если она сама эпик
    внутри RFA «целиком», её галочка ничего не меняет — «неактивен»."""
    db = testclient_db_session
    _seed(db)
    multi = '["Команда А", "Команда Б"]'
    _add(db, "RFA-60", participating=multi, **RFA)
    _add(db, "OS-60", parent="RFA-60", team=TEAM_B)
    _add(db, "RFA-70", **RFA)
    _add(db, "OS-70", parent="RFA-70", participating=multi)
    _add(db, "OS-71", parent="OS-70", team=TEAM_B)
    db.commit()

    roles = _roles(client, view="active")
    assert roles["bi-RFA-60"] == "by_epics_locked"
    assert roles["bi-OS-70"] == "inert"
    r = client.get("/api/v1/backlog/bi-OS-71")
    assert r.status_code == 200, r.text
    assert r.json()["in_plan_role"] == "regular"


def test_single_item_responses_carry_role(client, testclient_db_session):
    _seed(testclient_db_session)
    for item_id, role in (
        ("bi-OS-1", "inert"), ("bi-RFA-50", "by_epics"), ("bi-RFA-2", "regular"),
    ):
        r = client.get(f"/api/v1/backlog/{item_id}")
        assert r.status_code == 200, r.text
        assert r.json()["in_plan_role"] == role, item_id

    r = client.patch("/api/v1/backlog/bi-OS-1", json={"priority": 3})
    assert r.status_code == 200, r.text
    assert r.json()["in_plan_role"] == "inert"


def _list_query_count(client, engine) -> int:
    count = 0

    def _on_execute(*_args, **_kwargs):
        nonlocal count
        count += 1

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        r = client.get("/api/v1/backlog", params={"view": "active", "teams": TEAM_B})
        assert r.status_code == 200, r.text
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)
    return count


def test_roles_computed_without_per_row_queries(client, testclient_db_session):
    """Число запросов списка не растёт с числом групп."""
    db = testclient_db_session
    engine = db.get_bind()
    _seed(db)
    _list_query_count(client, engine)  # прогрев кэшей
    one = _list_query_count(client, engine)
    for n in (80, 81, 82):
        _add(db, f"RFA-{n}", **RFA)
        _add(db, f"OS-{n}", parent=f"RFA-{n}", team=TEAM_B)
        _add(db, f"RFA-{n + 10}", mode="by_epics", **RFA)
        _add(db, f"OS-{n + 10}", parent=f"RFA-{n + 10}", team=TEAM_B)
    db.commit()
    roles = _roles(client, view="active", teams=TEAM_B)
    assert [roles[f"bi-OS-{n}"] for n in (80, 81, 82)] == ["inert"] * 3
    assert _list_query_count(client, engine) == one
