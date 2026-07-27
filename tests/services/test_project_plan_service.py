"""ProjectPlanService: план/факт проекта по видам работ."""
import uuid
from datetime import date, datetime

import pytest

from app.models.backlog_item import BacklogItem
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.issue import Issue
from app.models.project import Project
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.models.worklog import Worklog
from app.services.project_plan_service import ProjectPlanService, _plural_projects


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


def test_children_include_own_subtree_hours(db_session):
    db = db_session
    _seed_project(db)

    plan = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)

    children = plan["children"]
    assert [c["key"] for c in children] == ["PP-2"], "только прямые дети корня"
    # 12 (свои) + 3 (внучка) + 20 (dev) + 5 (чужой) = 40ч по поддереву PP-2.
    assert children[0]["hours"] == 40.0
    assert children[0]["status"] == "Готово"
    assert children[0]["jira_url"].endswith("/PP-2")


def test_timeline_spans_all_quarters_of_the_project(db_session):
    db = db_session
    _seed_project(db)

    tl = ProjectPlanService(db).get_plan("PP-1", year=2026, quarter=3)["timeline"]

    assert tl["start"] == "2026-07-01"
    assert tl["end"] == "2026-10-20", "фаза следующего квартала не должна обрезаться"
    assert tl["quarter_start"] == "2026-07-01"
    assert tl["quarter_end"] == "2026-09-30"
    labels = [b["label"] for b in tl["rows"][0]["bars"]]
    assert labels == ["Анализ", "Разработка", "ОПЭ", "Тестирование"]


def test_timeline_empty_when_no_assignments(db_session):
    db = db_session
    db.add(Project(id="np2", jira_project_id="np2", key="NP2", name="No plan"))
    db.add(Issue(id="np2root", jira_issue_id="20", key="NP2-1", summary="Без плана",
                 issue_type="Epic", status="Новый", project_id="np2",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    db.commit()

    tl = ProjectPlanService(db).get_plan("NP2-1", year=2026, quarter=3)["timeline"]

    assert tl["start"] is None
    assert tl["rows"] == []


def test_project_without_team_and_plan_counts_everyone_as_internal(db_session):
    db = db_session
    db.add(Project(id="nt", jira_project_id="nt", key="NT", name="No team"))
    db.add(Issue(id="ntroot", jira_issue_id="30", key="NT-1", summary="Без команды",
                 issue_type="Epic", status="В работе", project_id="nt",
                 category="quarterly_tasks", include_in_analysis=True))
    emp = _employee(db, "Аналитик без команды", "analyst", None)
    _worklog(db, emp, "ntroot", 10.0, datetime(2026, 8, 1))
    db.commit()

    plan = ProjectPlanService(db).get_plan("NT-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    assert by_code["analyst"]["fact_hours"] == 10.0
    assert plan["external_hours"] == 0.0


def test_rp_role_hours_count_as_analyst(db_session):
    """Роль РП списывает часы в проекте — на столах РП считается аналитиком (спека §3.2)."""
    db = db_session
    db.add(Project(id="rp1", jira_project_id="rp1", key="RP1", name="RP project"))
    db.add(Issue(id="rproot", jira_issue_id="40", key="RP1-1", summary="РП считает в анализ",
                 issue_type="Epic", status="В работе", project_id="rp1",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    rp = _employee(db, "Руководитель проекта", "rp", "T")
    _worklog(db, rp, "rproot", 8.0, datetime(2026, 8, 1))
    db.commit()

    plan = ProjectPlanService(db).get_plan("RP1-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    assert by_code["analyst"]["fact_hours"] == 8.0
    assert by_code["dev"]["fact_hours"] == 0.0
    assert by_code["qa"]["fact_hours"] == 0.0
    assert plan["external_hours"] == 0.0


def test_children_sorted_by_hours_desc_then_key_tiebreak(db_session):
    db = db_session
    db.add(Project(id="srt", jira_project_id="srt", key="SRT", name="Sort test"))
    db.add(Issue(id="srtroot", jira_issue_id="50", key="SRT-1", summary="Проект сортировки",
                 issue_type="Epic", status="В работе", project_id="srt",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    db.add(Issue(id="srtA", jira_issue_id="51", key="SRT-9", summary="Больше всех",
                 issue_type="Task", status="В работе", project_id="srt",
                 parent_id="srtroot", include_in_analysis=True))
    db.add(Issue(id="srtB", jira_issue_id="52", key="SRT-5", summary="Тай-брейк, старший ключ",
                 issue_type="Task", status="В работе", project_id="srt",
                 parent_id="srtroot", include_in_analysis=True))
    db.add(Issue(id="srtC", jira_issue_id="53", key="SRT-3", summary="Тай-брейк, младший ключ",
                 issue_type="Task", status="В работе", project_id="srt",
                 parent_id="srtroot", include_in_analysis=True))
    worker = _employee(db, "Исполнитель", "dev", None)
    _worklog(db, worker, "srtA", 20.0, datetime(2026, 8, 1))
    _worklog(db, worker, "srtB", 8.0, datetime(2026, 8, 1))
    _worklog(db, worker, "srtC", 8.0, datetime(2026, 8, 1))
    db.commit()

    children = ProjectPlanService(db).get_plan("SRT-1", year=2026, quarter=3)["children"]

    assert [c["key"] for c in children] == ["SRT-9", "SRT-3", "SRT-5"]


def test_team_falls_back_to_plan_team_when_issue_team_empty(db_session):
    """Ветка «поле команды у эпика пустое → берём команду свежайшего плана»."""
    db = db_session
    db.add(Project(id="tpl", jira_project_id="tpl", key="TPL", name="Team from plan"))
    db.add(Issue(id="tplroot", jira_issue_id="60", key="TPL-1", summary="Без поля команда",
                 issue_type="Epic", status="В работе", project_id="tpl",
                 category="quarterly_tasks", include_in_analysis=True))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Без поля команда", issue_id="tplroot",
                       estimate_analyst_hours=10.0))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=10.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 20)))
    emp = _employee(db, "Аналитик команды Т", "analyst", "T")
    _worklog(db, emp, "tplroot", 6.0, datetime(2026, 7, 10))
    db.commit()

    plan = ProjectPlanService(db).get_plan("TPL-1", year=2026, quarter=3)

    by_code = {w["code"]: w for w in plan["work_types"]}
    assert by_code["analyst"]["fact_hours"] == 6.0
    assert by_code["analyst"]["plan_hours"] == 10.0
    assert plan["external_hours"] == 0.0


# ---------------------------------------------------------------------
# get_portfolio
# ---------------------------------------------------------------------

def test_portfolio_sums_projects_and_keeps_external_apart(db_session):
    db = db_session
    _seed_project(db)

    pf = ProjectPlanService(db).get_portfolio(["PP-1"], year=2026, quarter=3)

    assert pf["project_count"] == 1
    assert pf["total_plan"] == 130.0
    assert pf["total_fact"] == 35.0
    assert pf["total_pct"] == 27
    assert pf["external_hours"] == 5.0
    assert [r["key"] for r in pf["timeline"]["rows"]] == ["PP-1"]


def test_portfolio_signal_overload(db_session):
    db = db_session
    db.add(Project(id="ov", jira_project_id="ov", key="OV", name="Overload"))
    db.add(Issue(id="ovroot", jira_issue_id="30", key="OV-1", summary="Перегруз",
                 issue_type="Epic", status="В работе", project_id="ov",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Перегруз", issue_id="ovroot"))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=10.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 30)))
    emp = _employee(db, "Аналитик", "analyst", "T")
    _worklog(db, emp, "ovroot", 25.0, datetime(2026, 7, 15))
    db.commit()

    pf = ProjectPlanService(db).get_portfolio(["OV-1"], year=2026, quarter=3)

    kinds = {s["kind"] for s in pf["signals"]}
    assert "overload" in kinds
    overload = next(s for s in pf["signals"] if s["kind"] == "overload")
    assert "1" in overload["text"]


def test_portfolio_empty_list(db_session):
    pf = ProjectPlanService(db_session).get_portfolio([], year=2026, quarter=3)
    assert pf["project_count"] == 0
    assert pf["total_plan"] is None
    assert pf["signals"] == []


def test_portfolio_signal_silent(db_session):
    """Последнее списание больше 14 дней до конца квартала — сигнал «молчит»."""
    db = db_session
    db.add(Project(id="sl", jira_project_id="sl", key="SL", name="Silent"))
    db.add(Issue(id="slroot", jira_issue_id="31", key="SL-1", summary="Молчит",
                 issue_type="Epic", status="В работе", project_id="sl",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Молчит", issue_id="slroot"))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=20.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 30)))
    emp = _employee(db, "Аналитик", "analyst", "T")
    # Последнее (и единственное) списание 1 августа — до конца квартала (30 сентября)
    # больше 14 дней тишины.
    _worklog(db, emp, "slroot", 10.0, datetime(2026, 8, 1))
    db.commit()

    pf = ProjectPlanService(db).get_portfolio(["SL-1"], year=2026, quarter=3)

    assert pf["signals"] == [
        {"kind": "silent", "text": "1 проект без списаний 14+ дней", "severity": "warn"},
    ]


def test_portfolio_no_worklogs_is_not_silent(db_session):
    """Проект вообще без списаний — это «ещё не начинали», а не «замолчал»."""
    db = db_session
    db.add(Project(id="nw", jira_project_id="nw", key="NW", name="No worklogs"))
    db.add(Issue(id="nwroot", jira_issue_id="32", key="NW-1", summary="Не начинали",
                 issue_type="Epic", status="Новый", project_id="nw",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Не начинали", issue_id="nwroot"))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=20.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 30)))
    db.commit()

    pf = ProjectPlanService(db).get_portfolio(["NW-1"], year=2026, quarter=3)

    assert pf["signals"] == []


def test_portfolio_signal_lagging(db_session):
    """Вид работ, сильно отстающий от общего процента, — отдельный сигнал."""
    db = db_session
    db.add(Project(id="lg", jira_project_id="lg", key="LG", name="Lagging"))
    db.add(Issue(id="lgroot", jira_issue_id="33", key="LG-1", summary="Разработка тормозит",
                 issue_type="Epic", status="В работе", project_id="lg",
                 category="quarterly_tasks", include_in_analysis=True, team="T"))
    item_id = _uid()
    db.add(BacklogItem(id=item_id, title="Разработка тормозит", issue_id="lgroot"))
    plan_id = _uid()
    db.add(ResourcePlan(id=plan_id, team="T", year=2026, quarter="Q3",
                        computed_at=datetime(2026, 7, 20)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="analyst", hours_allocated=100.0,
                                  start_date=date(2026, 7, 1), end_date=date(2026, 7, 31)))
    db.add(ResourcePlanAssignment(id=_uid(), plan_id=plan_id, backlog_item_id=item_id,
                                  phase="dev", hours_allocated=100.0,
                                  start_date=date(2026, 8, 1), end_date=date(2026, 8, 31)))
    analyst = _employee(db, "Аналитик", "analyst", "T")
    # Аналитик всё сдал, разработка ещё не начата; списание близко к концу
    # квартала — «молчит» сработать не должно.
    _worklog(db, analyst, "lgroot", 100.0, datetime(2026, 9, 25))
    db.commit()

    pf = ProjectPlanService(db).get_portfolio(["LG-1"], year=2026, quarter=3)

    assert pf["signals"] == [
        {"kind": "lagging", "text": "Разработка отстаёт: 0% при 50% общей", "severity": "info"},
    ]


@pytest.mark.parametrize(
    "n,expected",
    [
        (1, "проект"),
        (2, "проекта"),
        (5, "проектов"),
        (11, "проектов"),
        (21, "проект"),
        (22, "проекта"),
        (25, "проектов"),
        (111, "проектов"),
        (112, "проектов"),
    ],
)
def test_plural_projects(n, expected):
    assert _plural_projects(n) == expected
