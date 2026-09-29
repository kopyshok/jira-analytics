"""Подбор разработчика с учётом группы внутри команды (мягкий приоритет)."""
import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.endpoints.resource_planning import _other_subgroup_ids
from app.database import get_db
from app.main import app
from app.models import BacklogItem, Employee, Issue, Project, ResourcePlan, ResourcePlanAssignment
from app.models.employee_team import EmployeeTeam
from app.models.team import Team, TeamSubgroup
from app.services.resource_planning_service import ResourcePlanningService
from tests.subgroup_fixtures import share


@pytest.fixture
def client(db_session):
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _subgroup(db_session, key: str, team_name: str = "T1") -> str:
    """Реальная строка группы: на Postgres внешний ключ распределения проверяется."""
    row = db_session.query(Team).filter(Team.name == team_name).first()
    if row is None:
        row = Team(name=team_name, has_subgroups=True)
        db_session.add(row)
        db_session.commit()
        db_session.refresh(row)
    sub = (
        db_session.query(TeamSubgroup)
        .filter(TeamSubgroup.team_id == row.id, TeamSubgroup.name == key)
        .first()
    )
    if sub is None:
        sub = TeamSubgroup(team_id=row.id, name=key)
        db_session.add(sub)
        db_session.commit()
        db_session.refresh(sub)
    return sub.id


def _emp(db_session, name: str, subgroup: str | None, team: str = "T1") -> Employee:
    e = Employee(
        jira_account_id=f"acc-{uuid.uuid4().hex[:12]}",
        display_name=name,
        role="developer",
        team=team,
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    subgroup_id = _subgroup(db_session, subgroup, team) if subgroup else None
    db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
    if subgroup_id:
        db_session.add(share(e.id, team, subgroup_id))
    db_session.commit()
    return e


def _emp_shared(
    db_session, name: str, shares: dict[str, int], team: str = "T1"
) -> Employee:
    """Сотрудник, сразу поделённый между несколькими группами (доля с начала участия)."""
    e = Employee(
        jira_account_id=f"acc-{uuid.uuid4().hex[:12]}",
        display_name=name,
        role="developer",
        team=team,
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    db_session.add(EmployeeTeam(employee_id=e.id, team=team, is_primary=True))
    for subgroup_id, percent in shares.items():
        db_session.add(share(e.id, team, subgroup_id, percent))
    db_session.commit()
    return e


def _item(db_session, dev_hours: float, priority: int) -> BacklogItem:
    item = BacklogItem(
        title=f"Init {priority}",
        estimate_analyst_hours=0.0,
        estimate_dev_hours=dev_hours,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        priority=priority,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_dev_from_own_subgroup(db_session):
    """Свой разработчик группы берётся, даже если сосед свободнее."""
    own = _emp(db_session, "Свой", "g1")
    neighbour = _emp(db_session, "Сосед", "g2")
    a = _item(db_session, 100.0, 9)
    b = _item(db_session, 100.0, 8)
    svc = ResourcePlanningService(db_session)
    res = svc._assign_employees(
        [a, b],
        [own, neighbour],
        emp_group={own.id: {"g1"}, neighbour.id: {"g2"}},
        item_group={a.id: "g1", b.id: "g1"},
        capacity={own.id: 400.0, neighbour.id: 400.0},
    )
    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == own.id


def test_neighbour_taken_when_own_out_of_capacity(db_session):
    """Свой выбрал ёмкость квартала — работа уходит свободному соседу."""
    own = _emp(db_session, "Свой", "g1")
    neighbour = _emp(db_session, "Сосед", "g2")
    a = _item(db_session, 90.0, 9)
    b = _item(db_session, 90.0, 8)
    svc = ResourcePlanningService(db_session)
    res = svc._assign_employees(
        [a, b],
        [own, neighbour],
        emp_group={own.id: {"g1"}, neighbour.id: {"g2"}},
        item_group={a.id: "g1", b.id: "g1"},
        capacity={own.id: 100.0, neighbour.id: 400.0},
    )
    # приоритетная задача осталась у своего, следующая ушла соседу
    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == neighbour.id


def test_no_subgroups_keeps_old_behaviour(db_session):
    """Команда без деления — прежний greedy по минимальной нагрузке."""
    e1 = _emp(db_session, "Первый", None)
    e2 = _emp(db_session, "Второй", None)
    a = _item(db_session, 100.0, 9)
    b = _item(db_session, 100.0, 8)
    svc = ResourcePlanningService(db_session)
    res = svc._assign_employees([a, b], [e1, e2])
    assert {res["dev"][a.id], res["dev"][b.id]} == {e1.id, e2.id}


def test_shared_employee_is_own_for_both_groups(db_session):
    """Общий сотрудник (A 60 / B 40) — свой и для задачи A, и для задачи B.

    Карты групп строятся `_subgroup_context` из реальных записей
    распределения и группы задач — из `effective_subgroup_id` их Issue, не
    руками. При равной загрузке общий подбирается раньше соседа из третьей
    (тоже настоящей) группы.
    """
    ga = _subgroup(db_session, "A", "T3")
    gb = _subgroup(db_session, "B", "T3")
    gc = _subgroup(db_session, "C", "T3")
    shared = _emp_shared(db_session, "Общий", {ga: 60, gb: 40}, "T3")
    neighbour = _emp(db_session, "Сосед", "C", "T3")
    item_a = _item(db_session, 50.0, 9)
    item_b = _item(db_session, 50.0, 8)
    item_a.issue = _issue_with_group(db_session, "T3-1", "T3", ga)
    item_b.issue = _issue_with_group(db_session, "T3-2", "T3", gb)
    db_session.commit()
    plan = ResourcePlan(team="T3", quarter="Q1", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    emp_group, item_group = svc._subgroup_context(
        plan, [shared, neighbour], [item_a, item_b], date(2026, 1, 1), date(2026, 3, 31)
    )
    assert emp_group[shared.id] == {ga, gb}
    assert emp_group[neighbour.id] == {gc}
    assert item_group == {item_a.id: ga, item_b.id: gb}

    res = svc._assign_employees(
        [item_a, item_b],
        [shared, neighbour],
        emp_group=emp_group,
        item_group=item_group,
        capacity={shared.id: 400.0, neighbour.id: 400.0},
    )
    assert res["dev"][item_a.id] == shared.id
    assert res["dev"][item_b.id] == shared.id


def test_subgroup_context_transfer_gives_both_groups_with_fallback_on_transfer_date(
    db_session,
):
    """Перевод внутри квартала: за квартал у сотрудника обе группы, а
    фолбэк-группа безымянной задачи — та, что действует на опорный день
    (сегодня, прижатое к концу квартала — оно позже 31.03.2026)."""
    ga = _subgroup(db_session, "A", "T4")
    gb = _subgroup(db_session, "B", "T4")
    emp = _emp(db_session, "Переведённый", "A", "T4")  # запись A с начала участия
    db_session.add(share(emp.id, "T4", gb, 100, date(2026, 2, 15)))
    item_no_issue = _item(db_session, 10.0, 9)
    item_no_issue.assignee_employee_id = emp.id
    db_session.commit()
    plan = ResourcePlan(team="T4", quarter="Q1", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    emp_group, item_group = svc._subgroup_context(
        plan, [emp], [item_no_issue], date(2026, 1, 1), date(2026, 3, 31)
    )

    assert emp_group[emp.id] == {ga, gb}
    assert item_group[item_no_issue.id] == gb


def test_subgroup_context_split_assignee_item_has_no_fallback_group(db_session):
    """Поделённый исполнитель без своей группы у задачи — фолбэка нет: доля
    не даёт однозначную группу для лесенки инициативы."""
    ga = _subgroup(db_session, "A", "T5")
    gb = _subgroup(db_session, "B", "T5")
    shared = _emp_shared(db_session, "Общий", {ga: 60, gb: 40}, "T5")
    item_no_issue = _item(db_session, 10.0, 9)
    item_no_issue.assignee_employee_id = shared.id
    db_session.commit()
    plan = ResourcePlan(team="T5", quarter="Q1", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    _, item_group = svc._subgroup_context(
        plan, [shared], [item_no_issue], date(2026, 1, 1), date(2026, 3, 31)
    )

    assert item_no_issue.id not in item_group


def test_subgroup_context_clips_groups_to_membership_inside_quarter(db_session):
    """Старая запись «с начала участия» до фактического вступления в команду
    в группы квартала не попадает — группы считаем от даты членства, а не
    от начала квартала плана."""
    ga = _subgroup(db_session, "A", "T6")
    gb = _subgroup(db_session, "B", "T6")
    emp = Employee(
        jira_account_id="acc-t6",
        display_name="Пришедший",
        role="developer",
        team="T6",
        is_active=True,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    db_session.add(
        EmployeeTeam(
            employee_id=emp.id, team="T6", is_primary=True, joined_at=date(2026, 2, 1)
        )
    )
    # Запись A действует «с начала участия» — до вступления сотрудника в
    # команду 01.02 её как будто не существовало.
    db_session.add(share(emp.id, "T6", ga, 100, None))
    db_session.add(share(emp.id, "T6", gb, 100, date(2026, 2, 1)))
    db_session.commit()
    plan = ResourcePlan(team="T6", quarter="Q1", year=2026, status="ready")
    db_session.add(plan)
    db_session.commit()

    svc = ResourcePlanningService(db_session)
    emp_group, _ = svc._subgroup_context(
        plan, [emp], [], date(2026, 1, 1), date(2026, 3, 31)
    )

    assert emp_group[emp.id] == {gb}


def test_pick_in_group_member_of_multiple_groups(db_session):
    """`_pick_in_group` с картой множеств: для группы B выбирается e1 (A и B)."""
    svc = ResourcePlanningService(db_session)
    result = svc._pick_in_group(
        ["e1", "e2"],
        "B",
        load={"e1": 0.0, "e2": 0.0},
        hours=10.0,
        emp_group={"e1": {"A", "B"}, "e2": {"C"}},
        capacity={"e1": 100.0, "e2": 100.0},
    )
    assert result == "e1"


def _issue_with_group(db_session, key: str, team: str, effective_subgroup_id) -> Issue:
    proj = db_session.query(Project).filter_by(key="RPT").first()
    if proj is None:
        proj = Project(jira_project_id="rpt", key="RPT", name="RPT")
        db_session.add(proj)
        db_session.flush()
    issue = Issue(
        jira_issue_id=f"j-{key}",
        key=key,
        summary="x",
        issue_type="Task",
        status="Open",
        project_id=proj.id,
        team=team,
        effective_subgroup_id=effective_subgroup_id,
    )
    db_session.add(issue)
    db_session.flush()
    return issue


def _plan_assignment(db_session, plan, item, employee, start, end) -> ResourcePlanAssignment:
    a = ResourcePlanAssignment(
        plan_id=plan.id,
        backlog_item_id=item.id,
        phase="dev",
        employee_id=employee.id if employee else None,
        start_date=start,
        end_date=end,
    )
    db_session.add(a)
    db_session.flush()
    return a


def test_other_subgroup_marker(db_session):
    """Задача своей группы — без метки; задача чужой группы — с меткой."""
    ga = _subgroup(db_session, "A", "T2")
    gb = _subgroup(db_session, "B", "T2")
    emp = _emp(db_session, "Иванов", "A", "T2")
    plan = ResourcePlan(team="T2", quarter="Q1", year=2026, status="ready")
    item_own = BacklogItem(title="own")
    item_other = BacklogItem(title="other")
    db_session.add_all([plan, item_own, item_other])
    db_session.flush()
    item_own.issue = _issue_with_group(db_session, "RPT-1", "T2", ga)
    item_other.issue = _issue_with_group(db_session, "RPT-2", "T2", gb)
    db_session.flush()
    a_own = _plan_assignment(
        db_session, plan, item_own, emp, date(2026, 1, 5), date(2026, 1, 10)
    )
    a_other = _plan_assignment(
        db_session, plan, item_other, emp, date(2026, 1, 5), date(2026, 1, 10)
    )
    db_session.commit()

    marked = _other_subgroup_ids(db_session, plan, [a_own, a_other])
    assert marked == {a_other.id}


def test_other_subgroup_marker_no_division_team(db_session):
    """Команда без деления на группы — метки никогда нет, даже если в
    данных остались группа задачи и доля исполнителя в другой группе
    (например, деление выключили и не почистили старые записи)."""
    team = Team(name="Plain", has_subgroups=False)
    db_session.add(team)
    db_session.flush()
    ga = _subgroup(db_session, "A", "Plain")
    gb = _subgroup(db_session, "B", "Plain")
    emp = Employee(
        jira_account_id="acc-plain-rp", display_name="X", is_active=True, team="Plain"
    )
    db_session.add(emp)
    db_session.flush()
    db_session.add(EmployeeTeam(employee_id=emp.id, team="Plain", is_primary=True))
    db_session.add(share(emp.id, "Plain", ga))
    plan = ResourcePlan(team="Plain", quarter="Q1", year=2026, status="ready")
    item = BacklogItem(title="i")
    db_session.add_all([plan, item])
    db_session.flush()
    item.issue = _issue_with_group(db_session, "RPT-3", "Plain", gb)
    db_session.flush()
    a = _plan_assignment(db_session, plan, item, emp, date(2026, 1, 1), date(2026, 1, 2))
    db_session.commit()

    assert _other_subgroup_ids(db_session, plan, [a]) == set()


def test_other_subgroup_marker_no_records_covering_dates(db_session):
    """Единственная запись распределения начинается позже дат назначения —
    сравнивать не с чем, метки нет (а не «все дни чужие»)."""
    ga = _subgroup(db_session, "A", "T8")
    gb = _subgroup(db_session, "B", "T8")
    emp = Employee(
        jira_account_id="acc-t8",
        display_name="Иванов",
        role="developer",
        team="T8",
        is_active=True,
    )
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    db_session.add(EmployeeTeam(employee_id=emp.id, team="T8", is_primary=True))
    db_session.add(share(emp.id, "T8", ga, 100, date(2026, 1, 1)))
    plan = ResourcePlan(team="T8", quarter="Q1", year=2026, status="ready")
    item = BacklogItem(title="i")
    db_session.add_all([plan, item])
    db_session.flush()
    item.issue = _issue_with_group(db_session, "RPT-4", "T8", gb)
    db_session.flush()
    a = _plan_assignment(db_session, plan, item, emp, date(2025, 1, 1), date(2025, 1, 2))
    db_session.commit()

    assert _other_subgroup_ids(db_session, plan, [a]) == set()


def test_gantt_marks_assignments_outside_employee_subgroup(client, db_session):
    """Диаграмма плана делённой команды: у задачи своей группы `other_subgroup`
    — false, у задачи чужой группы — true."""
    ga = _subgroup(db_session, "A", "T9")
    gb = _subgroup(db_session, "B", "T9")
    emp = _emp(db_session, "Иванов", "A", "T9")
    plan = ResourcePlan(team="T9", quarter="Q1", year=2026, status="ready")
    item_own = BacklogItem(title="own", estimate_dev_hours=1.0)
    item_other = BacklogItem(title="other", estimate_dev_hours=1.0)
    db_session.add_all([plan, item_own, item_other])
    db_session.flush()
    item_own.issue = _issue_with_group(db_session, "RPT-5", "T9", ga)
    item_other.issue = _issue_with_group(db_session, "RPT-6", "T9", gb)
    db_session.flush()
    a_own = _plan_assignment(
        db_session, plan, item_own, emp, date(2026, 1, 5), date(2026, 1, 6)
    )
    a_other = _plan_assignment(
        db_session, plan, item_other, emp, date(2026, 1, 5), date(2026, 1, 6)
    )
    db_session.commit()

    r = client.get(f"/api/v1/resource-planning/resource-plans/{plan.id}/gantt")
    assert r.status_code == 200, r.text
    by_id = {a["id"]: a for a in r.json()["assignments"]}

    assert by_id[a_own.id]["other_subgroup"] is False
    assert by_id[a_other.id]["other_subgroup"] is True
