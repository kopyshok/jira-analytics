"""Роль переключателя «В план» считает сервер — по всему бэклогу, а не по списку.

Список не видит всей группы RFA: родитель бывает чужой команды (фильтр), на
другой вкладке, утверждён или выполнен, а эпики спрятаны фильтром. Роль строки
сверяется с отбором кандидатов в сценарии: обычная — задача кандидат, «по
эпикам» — кандидат, только пока переключатель включён, «только по эпикам» и
«неактивен» — не кандидат при любом положении переключателя.
"""
import json
import random
from datetime import datetime
from typing import Callable, Optional

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.database import get_db
from app.main import app
from app.models import (
    AppSetting, BacklogItem, HierarchyRule, Issue, PlanningScenario, Project, ScenarioAllocation,
)
from app.services.backlog_service import (
    MULTI_TEAM_LOCK_KEY, mode_excluded_backlog_ids, mode_group_ids,
)

TEAM_A = "Команда А"
TEAM_B = "Команда Б"
TEAM_C = "Команда В"
RFA = {"project": "p-rfa", "issue_type": "RFA"}
MULTI = '["Команда А", "Команда Б"]'


@pytest.fixture
def client(testclient_db_session):
    app.dependency_overrides[get_db] = lambda: testclient_db_session
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _add(
    db, key: str, *, parent: Optional[str] = None, team: str = TEAM_A,
    project: str = "p-os", issue_type: str = "Epic", category: str = "initiatives_rfa",
    status_category: Optional[str] = None, participating: Optional[str] = None,
    mode: str = "whole", included: bool = True, archived: bool = False, backlog: bool = True,
) -> str:
    """Задача и её элемент бэклога ``bi-<key>``; ``backlog=False`` — только задача."""
    db.add(Issue(
        id=f"i-{key}", key=key, jira_issue_id=f"j-{key}", summary=key, issue_type=issue_type,
        status="Open", status_category=status_category, project_id=project,
        parent_id=f"i-{parent}" if parent else None, category=category, team=team,
        participating_teams=participating,
    ))
    db.flush()
    if backlog:
        db.add(BacklogItem(
            id=f"bi-{key}", issue_id=f"i-{key}", title=key, priority=1,
            planning_mode=mode, included_in_planning=included,
            archived_at=datetime(2026, 1, 1) if archived else None,
        ))
        db.flush()
    return f"bi-{key}"


def _base(db) -> None:
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


def _seed(db) -> None:
    _base(db)
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


def _seed_multi_team(db) -> None:
    """Мультикомандная RFA «целиком» с эпиком и мультикомандный эпик внутри
    RFA «целиком» со своим под-эпиком."""
    _add(db, "RFA-60", participating=MULTI, **RFA)
    _add(db, "OS-60", parent="RFA-60", team=TEAM_B)
    _add(db, "RFA-70", **RFA)
    _add(db, "OS-70", parent="RFA-70", participating=MULTI)
    _add(db, "OS-71", parent="OS-70", team=TEAM_B)
    db.commit()


def _lock_off(db) -> None:
    """Выключить в настройках планирование мультикомандных RFA только по эпикам."""
    db.add(AppSetting(key=MULTI_TEAM_LOCK_KEY, value="false"))
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


def _list_roles(client, lists: list[dict]) -> dict[str, str]:
    """Роли строк нескольких списков; в каждом списке у строки та же роль."""
    roles: dict[str, str] = {}
    for params in lists:
        for item_id, role in _roles(client, **params).items():
            assert roles.setdefault(item_id, role) == role, (params, item_id)
    return roles


def _single_roles(client, db) -> dict[str, str]:
    """Роль каждого элемента бэклога из его одиночного ответа."""
    roles: dict[str, str] = {}
    for (item_id,) in db.query(BacklogItem.id).all():
        r = client.get(f"/api/v1/backlog/{item_id}")
        assert r.status_code == 200, r.text
        roles[item_id] = r.json()["in_plan_role"]
    return roles


# Смысл роли для отбора кандидатов: исключена ли задача при включённом
# и при выключенном переключателе «В план».
EXCLUDED_BY_ROLE = {
    "regular": (False, False),
    "by_epics": (False, True),
    "by_epics_locked": (True, True),
    "inert": (True, True),
}


def _roles_match_selection(db, roles_of: Callable[[], dict[str, str]]) -> set[str]:
    """Сверить роли с отбором кандидатов при всех переключателях включённых,
    потом при всех выключенных. Роль от переключателя не зависит.
    Возвращает встреченные роли."""
    archived = {
        bid for (bid,) in db.query(BacklogItem.id).filter(BacklogItem.archived_at.isnot(None))
    }
    by_switch: dict[bool, dict[str, str]] = {}
    for on in (True, False):
        db.query(BacklogItem).update({BacklogItem.included_in_planning: on})
        db.commit()
        excluded = mode_excluded_backlog_ids(db)
        by_switch[on] = roles = roles_of()
        assert roles
        for item_id, role in roles.items():
            want = EXCLUDED_BY_ROLE[role][0 if on else 1]
            if role == "by_epics_locked" and item_id in archived:
                # RFA в архиве не кандидат и без режима группы.
                want = False
            assert (item_id in excluded) == want, (item_id, role, "on" if on else "off")
    assert by_switch[True] == by_switch[False]
    return set(by_switch[True].values())


LISTS = [
    {"view": "active"},
    {"view": "active", "teams": TEAM_A},
    {"view": "active", "teams": TEAM_B},
    {"view": "quarterly"},
    {"view": "quarterly", "teams": TEAM_A},
]


@pytest.mark.parametrize("lock", [True, False], ids=["lock-on", "lock-off"])
def test_role_matches_candidate_selection(client, testclient_db_session, lock):
    """Что роль строки обещает, то и делает отбор кандидатов — в любом списке."""
    db = testclient_db_session
    _seed(db)
    _seed_multi_team(db)
    if not lock:
        _lock_off(db)
    lists = [*LISTS, {"view": "in_work"}, {"view": "archived"}]
    seen = _roles_match_selection(db, lambda: _list_roles(client, lists))
    assert seen == {"regular", "by_epics", "inert"} | ({"by_epics_locked"} if lock else set())


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
    _seed_multi_team(db)

    roles = _roles(client, view="active")
    assert roles["bi-RFA-60"] == "by_epics_locked"
    assert roles["bi-OS-60"] == "regular"
    assert roles["bi-OS-70"] == "inert"
    r = client.get("/api/v1/backlog/bi-OS-71")
    assert r.status_code == 200, r.text
    assert r.json()["in_plan_role"] == "regular"


def test_lock_off_multi_team_follows_own_mode(client, testclient_db_session):
    """Блокировка выключена: мультикомандная RFA идёт по своему режиму.
    «Целиком» — сама включается как обычная, а её эпики неактивны, в том числе
    под-эпик мультикомандного эпика внутри RFA «целиком»."""
    db = testclient_db_session
    _seed(db)
    _seed_multi_team(db)
    _lock_off(db)

    rows = {row["id"]: row for row in client.get("/api/v1/backlog", params={"view": "active"}).json()}
    assert rows["bi-RFA-60"]["in_plan_role"] == "regular"
    assert rows["bi-RFA-60"]["include_locked"] is False
    roles = _roles(client, view="active")
    assert roles["bi-OS-60"] == "inert"
    assert roles["bi-OS-70"] == "inert"
    r = client.get("/api/v1/backlog/bi-OS-71")
    assert r.status_code == 200, r.text
    assert r.json()["in_plan_role"] == "inert"


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


def _issues_loaded(db, request) -> int:
    """Сколько задач поднял из базы запрос — с чистой сессии."""
    db.expunge_all()
    count = 0

    def _on_load(*_args):
        nonlocal count
        count += 1

    event.listen(Issue, "load", _on_load)
    try:
        r = request()
        assert r.status_code == 200, r.text
    finally:
        event.remove(Issue, "load", _on_load)
    return count


def test_roles_read_only_rows_of_response(client, testclient_db_session):
    """Роль считается по строкам ответа и их родителям: группы, которых в ответе
    нет, из базы не поднимаются — ни в одиночном ответе, ни в списке."""
    db = testclient_db_session
    _seed(db)

    def single():
        return client.get("/api/v1/backlog/bi-OS-1")

    def team_list():
        return client.get("/api/v1/backlog", params={"view": "active", "teams": TEAM_B})

    before = (_issues_loaded(db, single), _issues_loaded(db, team_list))
    for n in range(100, 130):
        _add(db, f"RFA-{n}", team=TEAM_C, **RFA)
        _add(db, f"OS-{n}", parent=f"RFA-{n}", team=TEAM_C)
    db.commit()
    assert (_issues_loaded(db, single), _issues_loaded(db, team_list)) == before


def _random_backlog(db, rng: random.Random) -> None:
    """Случайный бэклог: RFA → эпики → под-эпики разных команд и режимов, с Дискавери,
    мультикомандными, архивными, выполненными, квартальными и утверждёнными задачами,
    родителем вне бэклога и ручной идеей."""
    _base(db)
    teams = [TEAM_A, TEAM_B, TEAM_C]
    numbers = iter(range(1, 10_000))

    def attrs() -> dict:
        team = rng.choice(teams)
        participating = rng.choice([None, None, [team], [rng.choice(teams)], [TEAM_A, TEAM_B]])
        return {
            "team": team,
            "participating": json.dumps(participating, ensure_ascii=False) if participating else None,
            "mode": rng.choice(["whole", "whole", "by_epics"]),
            "included": rng.random() < 0.7,
            "archived": rng.random() < 0.15,
            "status_category": rng.choice([None, None, None, "indeterminate", "done"]),
            "category": rng.choice(["initiatives_rfa"] * 4 + ["quarterly_tasks"]),
        }

    def node(parent: Optional[str], depth: int) -> None:
        service = parent is not None and rng.random() < 0.25
        key = f"{'OS' if parent and not service else 'RFA'}-{next(numbers)}"
        kind = {"project": "p-rfa", "issue_type": "Эпик"} if service else RFA if not parent else {}
        in_backlog = parent is not None or rng.random() > 0.15
        _add(db, key, parent=parent, backlog=in_backlog, **kind, **attrs())
        for _ in range(rng.choice([0, 1, 2, 3] if depth == 0 else [0, 0, 1, 2] if depth == 1 else [0])):
            node(key, depth + 1)

    for _ in range(12):
        node(None, 0)
    db.add(PlanningScenario(id="s-appr", name="Утверждён", year=2026, quarter="Q3",
                            status="approved", team=TEAM_A))
    db.flush()
    items = sorted(db.query(BacklogItem).all(), key=lambda i: i.id)
    for n, item in enumerate(rng.sample(items, len(items) // 8)):
        db.add(ScenarioAllocation(scenario_id="s-appr", backlog_item_id=item.id,
                                  included_flag=True, planned_hours=0, sort_order=float(n)))
    db.add(BacklogItem(id="bi-manual", title="Идея без задачи", priority=1, team=TEAM_A))
    db.commit()


ALL_LISTS = [
    {"view": view, **({"teams": team} if team else {})}
    for view in ("active", "quarterly", "archived", "in_work")
    for team in (None, TEAM_A, TEAM_B)
]


@pytest.mark.parametrize("lock", [True, False], ids=["lock-on", "lock-off"])
@pytest.mark.parametrize("seed", range(4))
def test_random_backlog_roles_match_candidate_selection(client, testclient_db_session, seed, lock):
    """На случайном бэклоге роль каждого элемента — та, что делает отбор кандидатов."""
    db = testclient_db_session
    _random_backlog(db, random.Random(seed))
    if not lock:
        _lock_off(db)
    _roles_match_selection(db, lambda: _single_roles(client, db))


@pytest.mark.parametrize("lock", [True, False], ids=["lock-on", "lock-off"])
@pytest.mark.parametrize("seed", range(4))
def test_scoped_roles_match_whole_backlog(client, testclient_db_session, seed, lock):
    """Роль по строкам списка и одиночного ответа — та же, что по всему бэклогу."""
    db = testclient_db_session
    rng = random.Random(seed)
    _random_backlog(db, rng)
    if not lock:
        _lock_off(db)
    by_epics, whole_children = mode_group_ids(db, lock)

    def expected(item_id: str, locked: bool) -> str:
        if item_id in whole_children:
            return "inert"
        if locked:
            return "by_epics_locked"
        return "by_epics" if item_id in by_epics else "regular"

    for params in ALL_LISTS:
        r = client.get("/api/v1/backlog", params=params)
        assert r.status_code == 200, r.text
        for row in r.json():
            for rec in (row, *row["children"]):
                want = expected(rec["id"], rec["include_locked"])
                assert rec["in_plan_role"] == want, (params, rec["id"])

    items = sorted(db.query(BacklogItem).all(), key=lambda i: i.id)
    for item in rng.sample(items, 12):
        body = client.get(f"/api/v1/backlog/{item.id}").json()
        assert body["in_plan_role"] == expected(item.id, body["include_locked"]), item.id

    # Отбор задач: по ним — то же, что без отбора, лишнего не появляется.
    for _ in range(25):
        subset = rng.sample(items, rng.randint(1, 8))
        scope = {i.issue_id for i in subset if i.issue_id}
        scope |= {i.issue.parent_id for i in subset if i.issue is not None and i.issue.parent_id}
        scoped_by_epics, scoped_whole = mode_group_ids(db, lock, scope)
        ids = {i.id for i in subset}
        assert scoped_by_epics <= by_epics and scoped_whole <= whole_children
        assert scoped_by_epics & ids == by_epics & ids
        assert scoped_whole & ids == whole_children & ids
