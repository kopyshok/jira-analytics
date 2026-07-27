"""ProjectPlanService: план/факт проекта по видам работ."""
import uuid
from datetime import date, datetime

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.worklog import Worklog
from app.services.project_plan_service import ProjectPlanService


def _uid() -> str:
    return str(uuid.uuid4())


def _employee(db, name: str, role: str, team: str | None) -> str:
    eid = _uid()
    db.add(Employee(id=eid, jira_account_id=eid, display_name=name, role=role))
    if team:
        db.add(EmployeeTeam(id=_uid(), employee_id=eid, team=team, is_primary=True))
    return eid


def _worklog(db, employee_id: str, issue_id: str, hours: float, started: datetime) -> None:
    db.add(Worklog(id=_uid(), jira_worklog_id=_uid(), issue_id=issue_id,
                   employee_id=employee_id, hours=hours,
                   time_spent_seconds=int(hours * 3600), started_at=started))


def _seed_project(db) -> dict:
    """Эпик + подзадача + план на 2 квартала + свои и чужие списания."""
    db.add(Project(id="pp", jira_project_id="pp", key="PP", name="Project"))
    db.add(Issue(id="root", jira_issue_id="1", key="PP-1", summary="Проект",
                 issue_type="Epic", status="В работе", project_id="pp",
                 category="quarterly_tasks", include_in_analysis=True,
                 team="T"))
    db.add(Issue(id="kid", jira_issue_id="2", key="PP-2", summary="Подзадача",
                 issue_type="Task", status="Готово", project_id="pp",
                 parent_id="root", include_in_analysis=True))
    db.add(Issue(id="grandkid", jira_issue_id="3", key="PP-3", summary="Внучка",
                 issue_type="Sub-task", status="Готово", project_id="pp",
                 parent_id="kid", include_in_analysis=True))

    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Проект", issue_id="root",
                       estimate_analyst_hours=40.0, estimate_dev_hours=60.0,
                       estimate_qa_hours=20.0, estimate_opo_hours=10.0,
                       opo_analyst_ratio=0.5))

    q3_id, q4_id = _uid(), _uid()
    db.add(ResourcePlan(id=q3_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlan(id=q4_id, team="T", year=2026, quarter="Q4",
                        computed_at=datetime(2026, 10, 1)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q3_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=40.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 8, 15)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q3_id, backlog_item_id=item_id,
                                  phase="dev", hours_allocated=60.0,
                                  start_date=date(2026, 8, 16), end_date=date(2026, 9, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q4_id, backlog_item_id=item_id,
                                  phase="qa", hours_allocated=20.0,
                                  start_date=date(2026, 10, 1), end_date=date(2026, 10, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=q3_id, backlog_item_id=item_id,
                                  phase="opo", hours_allocated=10.0,
                                  start_date=date(2026, 9, 21), end_date=date(2026, 9, 30)))

    mine = _employee(db, "Свой аналитик", "analyst", "T")
    dev = _employee(db, "Свой разработчик", "dev", "T")
    alien = _employee(db, "Чужой", "analyst", "OTHER")
    # Списание раньше квартала — накопительный факт обязан его учесть.
    _worklog(db, mine, "kid", 12.0, datetime(2026, 6, 10))
    _worklog(db, mine, "grandkid", 3.0, datetime(2026, 7, 5))
    _worklog(db, dev, "kid", 20.0, datetime(2026, 8, 1))
    _worklog(db, alien, "kid", 5.0, datetime(2026, 8, 2))
    db.commit()
    return {"analyst": mine, "dev": dev, "alien": alien}


def test_plan_sums_across_quarters_and_splits_opo(db_session):
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    assert set(by_code) == {"analyst", "dev", "qa"}, "ОПЭ отдельным кольцом не показываем"
    # ОПЭ 10ч делится 50/50 между Анализом и Разработкой.
    assert by_code["analyst"]["plan_hours"] == 45.0
    assert by_code["dev"]["plan_hours"] == 65.0
    # Тестирование пришло из плана СЛЕДУЮЩЕГО квартала — горизонт весь проект.
    assert by_code["qa"]["plan_hours"] == 20.0
    assert plan["total_plan"] == 130.0


def test_fact_is_cumulative_over_subtree_and_excludes_outsiders(db_session):
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    # 12ч (до квартала) + 3ч (внучка) = 15ч аналитика.
    assert by_code["analyst"]["fact_hours"] == 15.0
    assert by_code["dev"]["fact_hours"] == 20.0
    assert plan["total_fact"] == 35.0
    # Чужие 5ч — только в отдельной плашке.
    assert plan["external_hours"] == 5.0


def test_plan_absent_returns_none_plan(db_session):
    db = db_session
    db.add(Project(id="np", jira_project_id="np", key="NP", name="No plan"))
    db.add(Issue(id="nproot", jira_issue_id="10", key="NP-1", summary="Без плана",
                 issue_type="Epic", status="Новый", project_id="np",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    db.commit()

    plan = ProjectPlanService(db).get_plan("NP-1", year=2026, quarter=3)

    assert plan["total_plan"] is None
    assert plan["total_pct"] is None
    assert plan["total_fact"] == 0.0


def test_unknown_key_returns_none(db_session):
    assert ProjectPlanService(db_session).get_plan("NOPE-1", year=2026, quarter=3) is None
