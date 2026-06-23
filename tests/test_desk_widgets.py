"""Тесты диспетчера и адаптеров виджетов рабочего стола.

Адаптеры проверяются на разреженном seed: контракт (топ-уровневые ключи и
типы значений) должен соблюдаться, пустые данные → пустые списки, без 500.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Comment,
    Employee,
    EmployeeTeam,
    Issue,
    Project,
    ResourcePlan,
    ResourcePlanAssignment,
    Worklog,
)
from app.services.work_desk_service import WorkDeskService
from app.services.work_desk_widgets import WIDGET_KEYS, desk_summary, dispatch


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
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def seed_employee(db_session):
    emp = Employee(
        id="emp-desk-1",
        jira_account_id="acc-desk-1",
        display_name="Стол Аналитик",
        avatar_url="https://example.com/a.png",
        is_active=True,
        role="analyst",
        team="Alpha",
        synced_at=datetime.utcnow(),
    )
    db_session.add(emp)
    db_session.add(EmployeeTeam(id="et-1", employee_id=emp.id, team="Alpha", is_primary=True))
    db_session.commit()
    return emp


def _current_quarter() -> tuple[int, int]:
    today = date.today()
    return today.year, (today.month - 1) // 3 + 1


# ── dispatcher + enabled-gate ───────────────────────────────────────────────


def test_widget_not_enabled_403(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    assert client.get(f"/api/v1/desk/{desk.token}/widget/my_tasks").status_code == 403


def test_widget_unknown_key_404(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["bogus"], "usr-1")
    assert client.get(f"/api/v1/desk/{desk.token}/widget/bogus").status_code == 404


def test_widget_enabled_returns_200(client, db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, ["hours_balance"], "usr-1")
    r = client.get(f"/api/v1/desk/{desk.token}/widget/hours_balance")
    assert r.status_code == 200
    assert "balance_hours" in r.json()


def test_dispatch_unknown_key_raises(db_session, seed_employee):
    desk = WorkDeskService().create(db_session, seed_employee.id, [], "usr-1")
    year, quarter = _current_quarter()
    with pytest.raises(ValueError):
        dispatch(db_session, desk, "nope", year, quarter)


def test_all_widget_keys_count():
    assert len(WIDGET_KEYS) == 9
    assert set(WIDGET_KEYS) == {
        "my_tasks",
        "my_timeline",
        "stale_tasks",
        "hours_balance",
        "category_breakdown",
        "team_absences",
        "team_availability",
        "production_calendar",
        "awaiting_reaction",
    }


# ── adapters: contract shape on sparse seed ─────────────────────────────────


def _make_desk(db_session, emp_id):
    return WorkDeskService().create(db_session, emp_id, list(WIDGET_KEYS), "usr-1")


def _dispatch(db_session, desk, key):
    year, quarter = _current_quarter()
    return dispatch(db_session, desk, key, year, quarter)


def test_my_tasks_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    assert isinstance(out["projects"], list)
    assert out["projects"] == []


def test_my_timeline_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_timeline")
    assert "quarter_start" in out
    assert "quarter_end" in out
    assert isinstance(out["bars"], list)
    assert out["bars"] == []


def test_hours_balance_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "hours_balance")
    assert isinstance(out["balance_hours"], float)
    assert isinstance(out["days"], list)


def test_category_breakdown_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "category_breakdown")
    assert isinstance(out["work_types"], list)
    assert out["work_types"] == []


def test_team_absences_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_absences")
    assert isinstance(out["employees"], list)
    assert isinstance(out["absences"], list)
    assert isinstance(out["year"], int)
    assert isinstance(out["quarter"], int)
    # Сотрудник стола состоит в команде Alpha — строка-сотрудник должна быть.
    assert any(e["id"] == seed_employee.id for e in out["employees"])
    assert out["absences"] == []


def test_team_availability_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_availability")
    assert isinstance(out["members"], list)
    assert out["members"] == []


def test_production_calendar_shape(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "production_calendar")
    assert isinstance(out["quarter_workdays"], int)
    assert isinstance(out["month_workdays"], int)
    assert isinstance(out["days"], list)
    assert out["quarter_workdays"] > 0  # квартал всегда содержит рабочие дни
    # дни покрывают весь квартал
    assert len(out["days"]) >= 89
    for d in out["days"][:1]:
        assert {"date", "kind", "hours"} <= set(d)


def test_awaiting_reaction_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "awaiting_reaction")
    assert isinstance(out["items"], list)
    assert out["items"] == []


def test_awaiting_reaction_with_comment(db_session, seed_employee):
    """Задача назначена сотруднику, не завершена, последний коммент — от другого."""
    other = Employee(
        id="emp-other",
        jira_account_id="acc-other",
        display_name="Коллега",
        is_active=True,
        synced_at=datetime.utcnow(),
    )
    proj = Project(
        id="proj-1",
        jira_project_id="10000",
        key="ALP",
        name="Alpha Project",
        synced_at=datetime.utcnow(),
    )
    db_session.add_all([other, proj])
    issue = Issue(
        id="iss-1",
        jira_issue_id="20000",
        key="ALP-1",
        summary="Нужен ответ",
        issue_type="Task",
        status="In Progress",
        status_category="indeterminate",
        project_id=proj.id,
        assignee_display_name="Стол Аналитик",
    )
    db_session.add(issue)
    db_session.add(
        Comment(
            id="cmt-1",
            jira_comment_id="c-1",
            body="Что по задаче?",
            jira_created_at=datetime(2026, 6, 10, 12, 0, 0),
            issue_id=issue.id,
            author_id=other.id,
            synced_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    desk = _make_desk(db_session, seed_employee.id)
    year, quarter = _current_quarter()
    out = dispatch(db_session, desk, "awaiting_reaction", year, quarter)
    assert len(out["items"]) == 1
    item = out["items"][0]
    assert item["key"] == "ALP-1"
    assert item["title"] == "Нужен ответ"
    assert item["last_comment_author"] == "Коллега"
    assert item["last_comment_at"] is not None


def test_awaiting_reaction_excludes_own_last_comment(db_session, seed_employee):
    """Если последний коммент написал сам сотрудник — мяч не на его стороне."""
    proj = Project(
        id="proj-2",
        jira_project_id="10001",
        key="ALP2",
        name="Alpha Project 2",
        synced_at=datetime.utcnow(),
    )
    db_session.add(proj)
    issue = Issue(
        id="iss-2",
        jira_issue_id="20001",
        key="ALP-2",
        summary="Я ответил",
        issue_type="Task",
        status="In Progress",
        status_category="indeterminate",
        project_id=proj.id,
        assignee_display_name="Стол Аналитик",
    )
    db_session.add(issue)
    db_session.add(
        Comment(
            id="cmt-2",
            jira_comment_id="c-2",
            body="Ответил",
            jira_created_at=datetime(2026, 6, 11, 9, 0, 0),
            issue_id=issue.id,
            author_id=seed_employee.id,
            synced_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    desk = _make_desk(db_session, seed_employee.id)
    year, quarter = _current_quarter()
    out = dispatch(db_session, desk, "awaiting_reaction", year, quarter)
    assert out["items"] == []


# ── stale_tasks: залежавшиеся задачи (PMD/OS, листовые, не done) ─────────────


def test_stale_tasks_empty(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "stale_tasks")
    assert out == {"my_tasks": [], "assigned": []}


def _stale_issue(db_session, **kw):
    defaults = dict(
        issue_type="Task",
        status="In Progress",
        status_category="indeterminate",
        participating_teams="[]",
    )
    defaults.update(kw)
    issue = Issue(**defaults)
    db_session.add(issue)
    return issue


def test_stale_tasks_split_and_filters(db_session, seed_employee):
    """Две колонки + фильтры: проект PMD/OS, не done, только листья."""
    other = Employee(
        id="emp-o", jira_account_id="acc-o", display_name="Коллега",
        is_active=True, synced_at=datetime.utcnow(),
    )
    pmd = Project(id="p-pmd", jira_project_id="1", key="PMD", name="PMD", synced_at=datetime.utcnow())
    os_p = Project(id="p-os", jira_project_id="2", key="OS", name="OS", synced_at=datetime.utcnow())
    itl = Project(id="p-itl", jira_project_id="3", key="ITL", name="ITL", synced_at=datetime.utcnow())
    db_session.add_all([other, pmd, os_p, itl])

    acct = seed_employee.jira_account_id
    # «Мои»: создал аналитик, исполнитель — другой, PMD, давно.
    _stale_issue(
        db_session, id="i-my", jira_issue_id="ji-my", key="PMD-1", summary="Моя забытая",
        project_id="p-pmd", reporter_account_id=acct, reporter_display_name="Стол Аналитик",
        assignee_account_id="acc-o", assignee_display_name="Коллега",
        status_changed_at=datetime(2026, 1, 10, 9, 0),
    )
    # «Задачи мне»: назначена аналитику, автор — другой, OS.
    _stale_issue(
        db_session, id="i-me", jira_issue_id="ji-me", key="OS-1", summary="Мне поручили",
        project_id="p-os", reporter_account_id="acc-o", reporter_display_name="Коллега",
        assignee_account_id=acct, assignee_display_name="Стол Аналитик",
        status_changed_at=datetime(2026, 2, 1, 9, 0),
    )
    # Завершённая — отсекается.
    _stale_issue(
        db_session, id="i-done", jira_issue_id="ji-done", key="PMD-2", summary="Готово",
        project_id="p-pmd", status="Done", status_category="done",
        assignee_account_id=acct, assignee_display_name="Стол Аналитик",
        status_changed_at=datetime(2026, 1, 1, 9, 0),
    )
    # Чужой проект ITL — отсекается.
    _stale_issue(
        db_session, id="i-itl", jira_issue_id="ji-itl", key="ITL-9", summary="Не наш проект",
        project_id="p-itl", assignee_account_id=acct, assignee_display_name="Стол Аналитик",
        status_changed_at=datetime(2026, 1, 1, 9, 0),
    )
    # Родитель с ребёнком в PMD — родитель отсекается (не лист), ребёнок назначен другому.
    _stale_issue(
        db_session, id="i-parent", jira_issue_id="ji-parent", key="PMD-3", summary="Родитель",
        project_id="p-pmd", assignee_account_id=acct, assignee_display_name="Стол Аналитик",
        status_changed_at=datetime(2026, 1, 5, 9, 0),
    )
    _stale_issue(
        db_session, id="i-child", jira_issue_id="ji-child", key="PMD-4", summary="Ребёнок",
        project_id="p-pmd", parent_id="i-parent", reporter_account_id="acc-o",
        assignee_account_id="acc-o", status_changed_at=datetime(2026, 1, 6, 9, 0),
    )
    db_session.commit()

    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "stale_tasks")

    my_keys = [t["key"] for t in out["my_tasks"]]
    assigned_keys = [t["key"] for t in out["assigned"]]
    assert my_keys == ["PMD-1"]
    assert assigned_keys == ["OS-1"]
    # Завершённая, чужой проект и родитель — не попали никуда.
    assert "PMD-2" not in my_keys + assigned_keys
    assert "ITL-9" not in my_keys + assigned_keys
    assert "PMD-3" not in my_keys + assigned_keys

    row = out["my_tasks"][0]
    assert row["person"]["name"] == "Коллега"
    assert row["url"].endswith("/browse/PMD-1")
    assert isinstance(row["days_idle"], int) and row["days_idle"] > 0


def test_stale_tasks_sorted_oldest_first_and_top10(db_session, seed_employee):
    """Сортировка по дате касания (старые сверху), не больше 10."""
    proj = Project(id="p-pmd2", jira_project_id="9", key="PMD", name="PMD", synced_at=datetime.utcnow())
    db_session.add(proj)
    acct = seed_employee.jira_account_id
    for n in range(12):
        _stale_issue(
            db_session, id=f"s-{n}", jira_issue_id=f"js-{n}", key=f"PMD-{100 + n}",
            summary=f"T{n}", project_id="p-pmd2", assignee_account_id=acct,
            assignee_display_name="Стол Аналитик",
            status_changed_at=datetime(2026, 1, 1) + timedelta(days=n),
        )
    db_session.commit()
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "stale_tasks")
    assigned = out["assigned"]
    assert len(assigned) == 10
    # Самая старая (день 1) — первой.
    assert assigned[0]["key"] == "PMD-100"
    days = [t["days_idle"] for t in assigned]
    assert days == sorted(days, reverse=True)


def test_stale_tasks_worklog_beats_old_status(db_session, seed_employee):
    """Свежий ворклог считается касанием — задача не выглядит старой."""
    proj = Project(id="p-pmd3", jira_project_id="11", key="PMD", name="PMD", synced_at=datetime.utcnow())
    db_session.add(proj)
    acct = seed_employee.jira_account_id
    # Статус не менялся давно, но ворклог — вчера.
    _stale_issue(
        db_session, id="i-wl", jira_issue_id="ji-wl", key="PMD-200", summary="Свежий ворклог",
        project_id="p-pmd3", assignee_account_id=acct, assignee_display_name="Стол Аналитик",
        status_changed_at=datetime(2025, 1, 1, 9, 0),
    )
    yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())
    db_session.add(
        Worklog(
            id="wl-stale", jira_worklog_id="jwl-stale", issue_id="i-wl",
            employee_id=seed_employee.id, started_at=yesterday,
            time_spent_seconds=3600, hours=1.0,
        )
    )
    db_session.commit()
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "stale_tasks")
    row = next(t for t in out["assigned"] if t["key"] == "PMD-200")
    # Касание — вчерашний ворклог, а не статус 2025 года.
    assert row["days_idle"] <= 1


# ── my_tasks: норма из оценки инициативы при пустом hours_allocated ──────────


def _seed_plan_with_assignment(
    db_session,
    *,
    employee_id: str,
    phase: str = "analyst",
    hours_allocated=None,
    estimate_analyst_hours=None,
):
    """Минимальный план команды Alpha за текущий квартал с одним назначением."""
    year, quarter = _current_quarter()
    plan = ResourcePlan(
        id="plan-1",
        team="Alpha",
        year=year,
        quarter=str(quarter),
        status="ready",
        computed_at=datetime.utcnow(),
    )
    item = BacklogItem(
        id="bi-1",
        title="Инициатива A",
        estimate_analyst_hours=estimate_analyst_hours,
    )
    db_session.add_all([plan, item])
    db_session.add(
        ResourcePlanAssignment(
            id="rpa-1",
            plan_id=plan.id,
            backlog_item_id=item.id,
            phase=phase,
            employee_id=employee_id,
            hours_allocated=hours_allocated,
        )
    )
    db_session.commit()
    return plan


def test_my_tasks_norm_falls_back_to_estimate(db_session, seed_employee):
    """hours_allocated пустой → норма берётся из оценки роли на инициативе."""
    _seed_plan_with_assignment(
        db_session,
        employee_id=seed_employee.id,
        phase="analyst",
        hours_allocated=None,
        estimate_analyst_hours=40.0,
    )
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    assert len(out["projects"]) == 1
    assert out["projects"][0]["norm_hours"] == 40.0


def test_my_tasks_norm_prefers_allocated(db_session, seed_employee):
    """hours_allocated задан → используется он, не оценка инициативы."""
    _seed_plan_with_assignment(
        db_session,
        employee_id=seed_employee.id,
        phase="analyst",
        hours_allocated=25.0,
        estimate_analyst_hours=40.0,
    )
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    assert out["projects"][0]["norm_hours"] == 25.0


def test_my_tasks_fact_sums_subtree_worklogs(db_session, seed_employee):
    """Факт проекта = списания по поддереву (на подзадаче, не на инициативе)."""
    year, quarter = _current_quarter()
    month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    proj = Project(id="prj-1", jira_project_id="10000", key="ITL", name="ITL", is_active=True)
    parent = Issue(
        id="iss-P", jira_issue_id="ji-P", key="ITL-1", summary="Инициатива",
        issue_type="Задача", status="In Progress", status_category="indeterminate",
        project_id="prj-1", participating_teams="[]",
    )
    child = Issue(
        id="iss-C", jira_issue_id="ji-C", key="ITL-2", summary="Подзадача",
        issue_type="Sub-task", status="In Progress", status_category="indeterminate",
        project_id="prj-1", parent_id="iss-P", participating_teams="[]",
    )
    item = BacklogItem(id="bi-1", title="Инициатива A", issue_id="iss-P")
    plan = ResourcePlan(
        id="plan-1", team="Alpha", year=year, quarter=str(quarter),
        status="ready", computed_at=datetime.utcnow(),
    )
    db_session.add_all([proj, parent, child, item, plan])
    db_session.add(
        ResourcePlanAssignment(
            id="rpa-1", plan_id="plan-1", backlog_item_id="bi-1",
            phase="analyst", employee_id=seed_employee.id, hours_allocated=10.0,
        )
    )
    db_session.add(
        Worklog(
            id="wl-1", jira_worklog_id="jwl-1", issue_id="iss-C",
            employee_id=seed_employee.id, started_at=datetime(year, month, 15, 10),
            time_spent_seconds=25200, hours=7.0,
        )
    )
    db_session.commit()
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    assert out["projects"][0]["fact_hours"] == 7.0
    assert out["projects"][0]["children"][0]["fact_hours"] == 7.0


def test_my_tasks_work_types_split_plan_and_fact_by_role(db_session, seed_employee):
    """Разбивка по 4 видам: план из всех фаз, факт по роли автора, итог = сумма."""
    year, quarter = _current_quarter()
    month = {1: 1, 2: 4, 3: 7, 4: 10}[quarter]
    dev = Employee(
        id="emp-dev", jira_account_id="acc-dev", display_name="Разработчик",
        is_active=True, role="dev", team="Alpha", synced_at=datetime.utcnow(),
    )
    proj = Project(id="prj-1", jira_project_id="10000", key="ITL", name="ITL", is_active=True)
    parent = Issue(
        id="iss-P", jira_issue_id="ji-P", key="ITL-1", summary="Инициатива",
        issue_type="Задача", status="In Progress", status_category="indeterminate",
        project_id="prj-1", participating_teams="[]",
    )
    item = BacklogItem(id="bi-1", title="Инициатива A", issue_id="iss-P")
    plan = ResourcePlan(
        id="plan-1", team="Alpha", year=year, quarter=str(quarter),
        status="ready", computed_at=datetime.utcnow(),
    )
    db_session.add_all([dev, proj, parent, item, plan])
    db_session.add_all([
        ResourcePlanAssignment(
            id="rpa-an", plan_id="plan-1", backlog_item_id="bi-1",
            phase="analyst", employee_id=seed_employee.id, hours_allocated=10.0,
        ),
        ResourcePlanAssignment(
            id="rpa-dev", plan_id="plan-1", backlog_item_id="bi-1",
            phase="dev", employee_id=dev.id, hours_allocated=20.0,
        ),
        ResourcePlanAssignment(
            id="rpa-opo", plan_id="plan-1", backlog_item_id="bi-1",
            phase="opo", employee_id=seed_employee.id, hours_allocated=10.0,
        ),
    ])
    db_session.add_all([
        Worklog(
            id="wl-an", jira_worklog_id="jwl-an", issue_id="iss-P",
            employee_id=seed_employee.id, started_at=datetime(year, month, 15, 10),
            time_spent_seconds=25200, hours=7.0,
        ),
        Worklog(
            id="wl-dev", jira_worklog_id="jwl-dev", issue_id="iss-P",
            employee_id=dev.id, started_at=datetime(year, month, 16, 10),
            time_spent_seconds=18000, hours=5.0,
        ),
    ])
    db_session.commit()
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "my_tasks")
    wt = {w["code"]: w for w in out["projects"][0]["work_types"]}
    # ОПЭ-плашки нет; её план (10ч) делится 50/50 на Анализ (+5) и Разработку (+5).
    assert "opo" not in wt
    assert wt["analyst"]["plan_hours"] == 15.0 and wt["analyst"]["fact_hours"] == 7.0
    assert wt["dev"]["plan_hours"] == 25.0 and wt["dev"]["fact_hours"] == 5.0
    assert wt["qa"]["plan_hours"] == 0.0
    assert out["projects"][0]["norm_hours"] == 40.0
    assert out["projects"][0]["fact_hours"] == 12.0


# ── team_availability: исключение разработчиков и сотрудника стола ───────────


def test_team_availability_excludes_dev_and_desk_employee(db_session, seed_employee):
    """В занятости команды нет ни самого сотрудника стола, ни разработчиков."""
    year, quarter = _current_quarter()
    dev = Employee(
        id="emp-dev",
        jira_account_id="acc-dev",
        display_name="Разработчик",
        is_active=True,
        role="dev",
        team="Alpha",
        synced_at=datetime.utcnow(),
    )
    analyst = Employee(
        id="emp-analyst",
        jira_account_id="acc-analyst",
        display_name="Аналитик-2",
        is_active=True,
        role="analyst",
        team="Alpha",
        synced_at=datetime.utcnow(),
    )
    db_session.add_all([dev, analyst])
    db_session.add_all(
        [
            EmployeeTeam(id="et-dev", employee_id=dev.id, team="Alpha", is_primary=True),
            EmployeeTeam(id="et-an", employee_id=analyst.id, team="Alpha", is_primary=True),
        ]
    )
    plan = ResourcePlan(
        id="plan-ta",
        team="Alpha",
        year=year,
        quarter=str(quarter),
        status="ready",
        computed_at=datetime.utcnow(),
    )
    item = BacklogItem(id="bi-ta", title="Инициатива", estimate_analyst_hours=10.0)
    db_session.add_all([plan, item])
    db_session.add_all(
        [
            ResourcePlanAssignment(
                id="rpa-desk", plan_id=plan.id, backlog_item_id=item.id,
                phase="analyst", employee_id=seed_employee.id, hours_allocated=8.0,
            ),
            ResourcePlanAssignment(
                id="rpa-dev", plan_id=plan.id, backlog_item_id=item.id,
                phase="dev", employee_id=dev.id, hours_allocated=8.0,
            ),
            ResourcePlanAssignment(
                id="rpa-an", plan_id=plan.id, backlog_item_id=item.id,
                phase="analyst", employee_id=analyst.id, hours_allocated=8.0,
            ),
        ]
    )
    db_session.commit()

    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "team_availability")
    member_ids = {m["id"] for m in out["members"]}
    assert seed_employee.id not in member_ids
    assert dev.id not in member_ids
    assert analyst.id in member_ids


# ── production_calendar: рабочие часы месяца и квартала ──────────────────────


def test_production_calendar_work_hours(db_session, seed_employee):
    desk = _make_desk(db_session, seed_employee.id)
    out = _dispatch(db_session, desk, "production_calendar")
    assert isinstance(out["month_work_hours"], float)
    assert isinstance(out["quarter_work_hours"], float)
    assert out["quarter_work_hours"] > 0


# ── desk_summary: hero-числа без падений на пустом seed ──────────────────────


def test_desk_summary_keys_no_plan(db_session, seed_employee):
    """У сотрудника без плана сводка отдаёт 3 числовых ключа, не падая."""
    desk = _make_desk(db_session, seed_employee.id)
    year, quarter = _current_quarter()
    out = desk_summary(db_session, desk, year, quarter)
    assert set(out) == {
        "overtime_hours",
        "remaining_workdays_month",
        "projects_in_progress",
    }
    assert isinstance(out["overtime_hours"], float)
    assert isinstance(out["remaining_workdays_month"], int)
    assert isinstance(out["projects_in_progress"], int)
    # Без плана незавершённых проектов нет.
    assert out["projects_in_progress"] == 0
    # До конца месяца всегда есть хотя бы один день (тест считая сегодня).
    assert out["remaining_workdays_month"] >= 0
