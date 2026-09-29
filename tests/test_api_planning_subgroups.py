"""Группа внутри команды в выдаче сценария: идеи и сотрудники."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import (
    BacklogItem,
    Employee,
    EmployeeTeam,
    Issue,
    PlanningScenario,
    ProductionCalendarDay,
    Project,
    ScenarioAllocation,
    Team,
    TeamSubgroup,
)
from tests.subgroup_fixtures import share

TEAM = "Команда 1С (Бухгалтерия)"


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
    def _get_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _seed(db, *, has_subgroups: bool) -> str:
    """Команда с двумя группами, сотрудник, задача и идея в сценарии."""
    db.add(Team(id="t-1", name=TEAM, has_subgroups=has_subgroups))
    db.flush()
    db.add_all(
        [
            TeamSubgroup(id="sg-1", team_id="t-1", name="Расчёты", sort_order=1),
            TeamSubgroup(id="sg-2", team_id="t-1", name="Интеграции", sort_order=2),
        ]
    )
    db.add(
        ProductionCalendarDay(
            date=date(2026, 1, 5), is_workday=True, kind="workday", hours=8.0,
            source="manual",
        )
    )
    db.add(
        Employee(
            id="e-1", jira_account_id="acc-1", display_name="Иванов Иван",
            role="dev", is_active=True,
        )
    )
    db.add(
        EmployeeTeam(
            employee_id="e-1", team=TEAM, is_primary=True,
            subgroup_id="sg-1" if has_subgroups else None,
        )
    )
    if has_subgroups:
        db.add(share("e-1", TEAM, "sg-1"))
    db.add(Project(id="p-1", jira_project_id="1", key="RFA", name="RFA"))
    db.add(
        Issue(
            id="i-1", jira_issue_id="10001", key="RFA-1", summary="Идея", issue_type="Task", status="Открыта", project_id="p-1", team=TEAM,
            category="initiatives_rfa",
            effective_subgroup_id="sg-2" if has_subgroups else None,
        )
    )
    db.add(
        BacklogItem(
            id="b-1", title="Идея", issue_id="i-1", assignee_employee_id="e-1",
        )
    )
    scenario = PlanningScenario(
        id="sc-1", name="План", quarter="Q1", year=2026, team=TEAM, status="draft",
    )
    db.add(scenario)
    db.flush()
    db.add(
        ScenarioAllocation(
            id="al-1", scenario_id="sc-1", backlog_item_id="b-1", included_flag=True,
        )
    )
    db.commit()
    return "sc-1"


def test_allocations_carry_subgroup(client, db_session):
    """Группа идеи берётся с задачи."""
    sid = _seed(db_session, has_subgroups=True)

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")

    assert r.status_code == 200, r.text
    rows = r.json()
    assert [row["subgroup_id"] for row in rows] == ["sg-2"]


def test_allocation_falls_back_to_assignee_group(client, db_session):
    """Идея без группы на задаче опирается на группу исполнителя."""
    sid = _seed(db_session, has_subgroups=True)
    issue = db_session.get(Issue, "i-1")
    issue.effective_subgroup_id = None
    db_session.commit()

    r = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")

    assert r.status_code == 200, r.text
    assert r.json()[0]["subgroup_id"] == "sg-1"


def test_resource_employees_carry_subgroup(client, db_session):
    sid = _seed(db_session, has_subgroups=True)

    r = client.get(f"/api/v1/planning/scenarios/{sid}/resource")

    assert r.status_code == 200, r.text
    assert r.json()["employees"][0]["subgroup_id"] == "sg-1"


def test_team_without_subgroups_stays_empty(client, db_session):
    """Признак деления выключен — раздел ведёт себя как до правки."""
    sid = _seed(db_session, has_subgroups=False)

    allocs = client.get(f"/api/v1/planning/scenarios/{sid}/allocations")
    resource = client.get(f"/api/v1/planning/scenarios/{sid}/resource")

    assert allocs.json()[0]["subgroup_id"] is None
    assert resource.json()["employees"][0]["subgroup_id"] is None


def test_allocation_without_issue_split_assignee_has_no_group(client, db_session):
    """Идея без задачи, исполнитель поделён 60/40 между группами — группы нет."""
    db_session.add(Team(id="t-split", name=TEAM, has_subgroups=True))
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id="sg-1", team_id="t-split", name="Расчёты", sort_order=1),
        TeamSubgroup(id="sg-2", team_id="t-split", name="Интеграции", sort_order=2),
    ])
    db_session.add(
        Employee(
            id="e-1", jira_account_id="acc-1", display_name="Иванов Иван",
            role="dev", is_active=True,
        )
    )
    db_session.add(EmployeeTeam(employee_id="e-1", team=TEAM, is_primary=True))
    db_session.add(share("e-1", TEAM, "sg-1", 60))
    db_session.add(share("e-1", TEAM, "sg-2", 40))
    db_session.add(
        BacklogItem(id="b-2", title="Идея без задачи", assignee_employee_id="e-1")
    )
    scenario = PlanningScenario(
        id="sc-2", name="План", quarter="Q1", year=2026, team=TEAM, status="draft",
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioAllocation(
            id="al-2", scenario_id="sc-2", backlog_item_id="b-2", included_flag=True,
        )
    )
    db_session.commit()

    r = client.get(f"/api/v1/planning/scenarios/{scenario.id}/allocations")

    assert r.status_code == 200, r.text
    assert r.json()[0]["subgroup_id"] is None


def test_allocation_transfer_uses_new_group_in_current_quarter(client, db_session):
    """Перевод с начала текущего квартала — идея без задачи получает новую группу."""
    from app.services.cross_team_occupancy import quarter_num
    from app.services.plan_common import quarter_bounds

    today = date.today()
    q = (today.month - 1) // 3 + 1
    quarter_start, _ = quarter_bounds(today.year, q)
    assert quarter_num(f"Q{q}") == q  # квартал вычислен корректно

    db_session.add(Team(id="t-transfer", name=TEAM, has_subgroups=True))
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id="sg-a", team_id="t-transfer", name="A", sort_order=1),
        TeamSubgroup(id="sg-b", team_id="t-transfer", name="B", sort_order=2),
    ])
    db_session.add(
        Employee(
            id="e-1", jira_account_id="acc-1", display_name="Иванов Иван",
            role="dev", is_active=True,
        )
    )
    db_session.add(EmployeeTeam(employee_id="e-1", team=TEAM, is_primary=True))
    db_session.add(share("e-1", TEAM, "sg-a"))
    db_session.add(share("e-1", TEAM, "sg-b", valid_from=quarter_start))
    db_session.add(
        BacklogItem(id="b-3", title="Идея без задачи", assignee_employee_id="e-1")
    )
    scenario = PlanningScenario(
        id="sc-3", name="План", quarter=f"Q{q}", year=today.year, team=TEAM,
        status="draft",
    )
    db_session.add(scenario)
    db_session.flush()
    db_session.add(
        ScenarioAllocation(
            id="al-3", scenario_id="sc-3", backlog_item_id="b-3", included_flag=True,
        )
    )
    db_session.commit()

    r = client.get(f"/api/v1/planning/scenarios/{scenario.id}/allocations")

    assert r.status_code == 200, r.text
    assert r.json()[0]["subgroup_id"] == "sg-b"


def test_resource_endpoint_returns_subgroup_hours_and_labels(client, db_session):
    """Разбивка по группам и подписи видны в ответе базы ресурса сотрудника."""
    db_session.add(Team(id="t-split2", name=TEAM, has_subgroups=True))
    db_session.flush()
    db_session.add_all([
        TeamSubgroup(id="sg-1", team_id="t-split2", name="Расчёты", sort_order=1),
        TeamSubgroup(id="sg-2", team_id="t-split2", name="Интеграции", sort_order=2),
    ])
    db_session.add(
        ProductionCalendarDay(
            date=date(2026, 1, 5), is_workday=True, kind="workday", hours=8.0,
            source="manual",
        )
    )
    db_session.add(
        Employee(
            id="e-1", jira_account_id="acc-1", display_name="Иванов Иван",
            role="dev", is_active=True,
        )
    )
    db_session.add(EmployeeTeam(employee_id="e-1", team=TEAM, is_primary=True))
    db_session.add(share("e-1", TEAM, "sg-1", 60))
    db_session.add(share("e-1", TEAM, "sg-2", 40))
    scenario = PlanningScenario(
        id="sc-4", name="План", quarter="Q1", year=2026, team=TEAM, status="draft",
    )
    db_session.add(scenario)
    db_session.commit()

    r = client.get(f"/api/v1/planning/scenarios/{scenario.id}/resource")

    assert r.status_code == 200, r.text
    emp = r.json()["employees"][0]
    assert emp["subgroup_labels"] == {"sg-1": "60%", "sg-2": "40%"}


def test_resource_summary_endpoint_lists_ungrouped_employees(client, db_session):
    """Сводка ресурса перечисляет активных сотрудников без группы."""
    sid = _seed(db_session, has_subgroups=True)
    db_session.add(
        Employee(
            id="e-2", jira_account_id="acc-2", display_name="Петров Пётр",
            role="dev", is_active=True,
        )
    )
    db_session.add(EmployeeTeam(employee_id="e-2", team=TEAM, is_primary=True))
    db_session.commit()

    r = client.get(f"/api/v1/planning/scenarios/{sid}/resource-summary")

    assert r.status_code == 200, r.text
    assert r.json()["ungrouped_employees"] == [
        {"employee_id": "e-2", "display_name": "Петров Пётр"}
    ]


def test_approve_blocked_while_employee_has_no_group(client, db_session):
    """Утверждение заблокировано, пока у активного сотрудника нет группы."""
    from app.models import ScenarioRevision

    sid = _seed(db_session, has_subgroups=True)
    db_session.add(
        Employee(
            id="e-2", jira_account_id="acc-2", display_name="Петров Пётр",
            role="dev", is_active=True,
        )
    )
    db_session.add(EmployeeTeam(employee_id="e-2", team=TEAM, is_primary=True))
    db_session.commit()

    blocked = client.post(f"/api/v1/planning/scenarios/{sid}/approve")

    assert blocked.status_code == 409, blocked.text
    detail = blocked.json()["detail"]
    assert "Петров Пётр" in detail
    assert "Иванов Иван" not in detail
    # Отказ — до любой записи: ни ревизии, ни смены статуса.
    db_session.expire_all()
    assert db_session.get(PlanningScenario, sid).status == "draft"
    assert db_session.query(ScenarioRevision).count() == 0

    db_session.add(share("e-2", TEAM, "sg-2"))
    db_session.commit()

    ok = client.post(f"/api/v1/planning/scenarios/{sid}/approve")

    assert ok.status_code == 200, ok.text
