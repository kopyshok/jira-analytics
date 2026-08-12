"""ProjectsService: list_projects + get_project_detail."""
import uuid
from datetime import datetime

from app.models.issue import Issue
from app.models.project import Project
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.models.employee_team import EmployeeTeam
from app.models.category import Category
from app.models.backlog_item import BacklogItem
from app.models.planning_scenario import PlanningScenario
from app.models.scenario_allocation import ScenarioAllocation
from app.services.projects_service import ProjectsService


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_project(db, pid: str, key: str, name: str = "Project") -> Project:
    p = Project(id=pid, jira_project_id=pid, key=key, name=name)
    db.add(p)
    db.commit()
    return p


def _make_category(db, code: str, label: str, color: str = "#000") -> Category:
    cat = db.query(Category).filter_by(code=code).first()
    if cat:
        return cat
    import uuid
    cat = Category(id=str(uuid.uuid4()), code=code, label=label, color=color, sort_order=1, is_system=False)
    db.add(cat)
    db.commit()
    return cat


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_list_projects_filters_by_quarterly_categories(db_session):
    db = db_session
    _make_project(db, "p1", "PRJ1")
    db.add(Issue(id="i1", jira_issue_id="1", key="PRJ1-1", summary="Q",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="quarterly_tasks", include_in_analysis=True))
    db.add(Issue(id="i2", jira_issue_id="2", key="PRJ1-2", summary="A",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="archive_target", include_in_analysis=True))
    db.add(Issue(id="i3", jira_issue_id="3", key="PRJ1-3", summary="X",
                 issue_type="Epic", status="Done", project_id="p1",
                 category="tech_debt", include_in_analysis=True))
    db.commit()

    items = ProjectsService(db).list_projects()
    keys = {item.key for item in items}
    assert "PRJ1-1" in keys
    assert "PRJ1-2" in keys
    assert "PRJ1-3" not in keys


def test_list_projects_includes_metrics(db_session):
    db = db_session
    _make_project(db, "p2", "PRJ2")
    parent = Issue(id="ip", jira_issue_id="100", key="PRJ2-100", summary="Parent",
                   issue_type="Epic", status="Done", project_id="p2",
                   category="quarterly_tasks", include_in_analysis=True)
    child = Issue(id="ic", jira_issue_id="101", key="PRJ2-101", summary="Child",
                  issue_type="Task", status="Done", project_id="p2",
                  parent_id="ip", category="tech_debt", include_in_analysis=True)
    emp = Employee(id="e1", jira_account_id="acc1", display_name="John", email="j@e", is_active=True)
    db.add_all([parent, child, emp])
    db.commit()

    db.add(Worklog(id="w1", jira_worklog_id="w1", issue_id="ic", employee_id="e1",
                   hours=10.0, time_spent_seconds=36000,
                   started_at=datetime(2026, 2, 12),
                   updated_at=datetime(2026, 2, 12)))
    db.add(Worklog(id="w2", jira_worklog_id="w2", issue_id="ic", employee_id="e1",
                   hours=5.0, time_spent_seconds=18000,
                   started_at=datetime(2026, 3, 25),
                   updated_at=datetime(2026, 3, 25)))
    db.commit()

    items = ProjectsService(db).list_projects()
    item = next((i for i in items if i.key == "PRJ2-100"), None)
    assert item is not None
    assert item.total_hours == 15.0
    assert item.child_count == 1
    assert item.employee_count == 1
    assert item.period_start == datetime(2026, 2, 12)
    assert item.period_end == datetime(2026, 3, 25)


def test_get_project_detail_aggregates(db_session):
    db = db_session
    _make_category(db, "tech_debt", "Tech Debt", "#00c9c8")
    _make_project(db, "p3", "PRJ3")
    parent = Issue(id="ip3", jira_issue_id="200", key="PRJ3-200", summary="Big",
                   issue_type="Epic", status="Done", project_id="p3",
                   category="quarterly_tasks", include_in_analysis=True,
                   rating_quality=5, rating_speed=4, rating_result=5)
    child = Issue(id="ic3", jira_issue_id="201", key="PRJ3-201", summary="Sub1",
                  issue_type="Task", status="Done", project_id="p3",
                  parent_id="ip3", category="tech_debt", include_in_analysis=True)
    e1 = Employee(id="e_a", jira_account_id="a1", display_name="Alice", email="a@e", is_active=True, team="A")
    e2 = Employee(id="e_b", jira_account_id="a2", display_name="Bob", email="b@e", is_active=True, team="B")
    db.add_all([parent, child, e1, e2])
    db.commit()

    db.add(Worklog(id="wa", jira_worklog_id="wa", issue_id="ic3", employee_id="e_a",
                   hours=20, time_spent_seconds=72000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.add(Worklog(id="wb", jira_worklog_id="wb", issue_id="ic3", employee_id="e_b",
                   hours=5, time_spent_seconds=18000,
                   started_at=datetime(2026, 2, 15), updated_at=datetime(2026, 2, 15)))
    db.commit()

    detail = ProjectsService(db).get_project_detail("PRJ3-200")
    assert detail is not None
    assert detail.key == "PRJ3-200"
    assert detail.total_hours == 25.0
    assert detail.employee_count == 2
    assert len(detail.categories) == 1
    assert detail.categories[0].code == "tech_debt"
    assert len(detail.employees) == 2
    assert detail.employees[0].name == "Alice"  # отсортированы по часам desc
    assert detail.employees[0].hours == 20.0
    assert detail.rating_quality == 5
    assert detail.rating_speed == 4
    assert detail.rating_result == 5


def test_get_project_detail_returns_detail_for_any_existing_issue(db_session):
    """Detail возвращает агрегаты для любого issue по key.

    Скоуп «проектности» определяется списком (фильтр сценария или
    категории) — на уровне detail просто отдаём данные.
    """
    db = db_session
    _make_project(db, "p4", "PRJ4")
    db.add(Issue(id="ix", jira_issue_id="300", key="PRJ4-300", summary="X",
                 issue_type="Epic", status="Done", project_id="p4",
                 category="tech_debt", include_in_analysis=True))
    db.commit()
    detail = ProjectsService(db).get_project_detail("PRJ4-300")
    assert detail is not None
    assert detail.key == "PRJ4-300"
    assert ProjectsService(db).get_project_detail("PRJ4-NOTEXIST") is None


def test_list_projects_filters_by_approved_scenario(db_session):
    """Только эпики, утверждённые в approved scenario для (year, quarter)."""
    db = db_session
    _make_project(db, "p_sc1", "SCN1")
    # Два эпика с категорией quarterly_tasks
    epic_in = Issue(id="sc_in", jira_issue_id="sc1", key="SCN1-1", summary="InScenario",
                    issue_type="Epic", status="Done", project_id="p_sc1",
                    category="quarterly_tasks", include_in_analysis=True)
    epic_out = Issue(id="sc_out", jira_issue_id="sc2", key="SCN1-2", summary="NotInScenario",
                     issue_type="Epic", status="Done", project_id="p_sc1",
                     category="quarterly_tasks", include_in_analysis=True)
    db.add_all([epic_in, epic_out])
    db.commit()

    # BacklogItem ссылается на epic_in
    item = BacklogItem(id=str(uuid.uuid4()), issue_id="sc_in", title="In")
    db.add(item)
    db.commit()

    # Approved scenario для 2026 Q2
    scenario = PlanningScenario(id=str(uuid.uuid4()), name="S1",
                                 year=2026, quarter="Q2", status="approved", team="T")
    db.add(scenario)
    db.commit()

    alloc = ScenarioAllocation(id=str(uuid.uuid4()), scenario_id=scenario.id,
                                backlog_item_id=item.id, included_flag=True)
    db.add(alloc)
    db.commit()

    # Без year/quarter — оба
    all_items = ProjectsService(db).list_projects()
    all_keys = {i.key for i in all_items}
    assert "SCN1-1" in all_keys
    assert "SCN1-2" in all_keys

    # С year=2026, quarter=2 — только SCN1-1
    filtered = ProjectsService(db).list_projects(year=2026, quarter=2)
    filtered_keys = {i.key for i in filtered}
    assert "SCN1-1" in filtered_keys
    assert "SCN1-2" not in filtered_keys

    # Другой квартал — пусто
    other_q = ProjectsService(db).list_projects(year=2026, quarter=3)
    assert other_q == []

    # team_filter совпадает с PlanningScenario.team="T" — проект есть
    with_team = ProjectsService(db).list_projects(year=2026, quarter=2, team_filter=["T"])
    assert any(i.key == "SCN1-1" for i in with_team)

    # team_filter не совпадает — пусто (сценарий фильтруется)
    wrong_team = ProjectsService(db).list_projects(year=2026, quarter=2, team_filter=["OTHER"])
    assert wrong_team == []


def test_list_projects_filters_by_team(db_session):
    """Глобальный team filter: проект попадает если есть worklog от сотрудника
    из выбранных команд."""
    db = db_session
    _make_project(db, "p5", "PRJ5")
    parent = Issue(id="ip5", jira_issue_id="400", key="PRJ5-400", summary="P",
                   issue_type="Epic", status="Done", project_id="p5",
                   category="quarterly_tasks", include_in_analysis=True)
    child = Issue(id="ic5", jira_issue_id="401", key="PRJ5-401", summary="S",
                  issue_type="Task", status="Done", project_id="p5",
                  parent_id="ip5", category="tech_debt", include_in_analysis=True)
    e_a = Employee(id="e_x", jira_account_id="x1", display_name="X", email="x@e", is_active=True, team="TeamA")
    e_b = Employee(id="e_y", jira_account_id="y1", display_name="Y", email="y@e", is_active=True, team="TeamB")
    db.add_all([parent, child, e_a, e_b])
    db.commit()
    db.add_all([
        EmployeeTeam(id="et_x", employee_id="e_x", team="TeamA", is_primary=True),
        EmployeeTeam(id="et_y", employee_id="e_y", team="TeamB", is_primary=True),
    ])
    db.commit()
    db.add(Worklog(id="wA", jira_worklog_id="wA", issue_id="ic5", employee_id="e_x",
                   hours=10, time_spent_seconds=36000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.commit()

    # Фильтруем по TeamB — нет ни одного worklog от TeamB → проект отсутствует
    items = ProjectsService(db).list_projects(team_filter=["TeamB"])
    assert all(i.key != "PRJ5-400" for i in items)

    # Фильтр по TeamA — проект есть
    items_a = ProjectsService(db).list_projects(team_filter=["TeamA"])
    assert any(i.key == "PRJ5-400" for i in items_a)


def test_list_project_keys_matches_list_projects_with_quarter_and_filters(db_session):
    """Лёгкий путь (только ключи, без обхода поддеревьев/ворклогов) обязан
    давать тот же набор, что list_projects, на всех комбинациях фильтров
    списка — команда/категория/статус/поиск. В квартальной ветке это точная
    эквивалентность: команда фильтруется на уровне запроса (через команду
    утверждённого сценария), до всякого обхода ворклогов.
    """
    db = db_session
    _make_project(db, "pk1", "PK1")

    epic_a = Issue(id="pka", jira_issue_id="900", key="PK1-1", summary="Alpha rollout",
                   issue_type="Epic", status="Новый", status_category="new",
                   project_id="pk1", category="quarterly_tasks", include_in_analysis=True)
    epic_b = Issue(id="pkb", jira_issue_id="901", key="PK1-2", summary="Beta project",
                   issue_type="Epic", status="Готово", status_category="done",
                   project_id="pk1", category="archive_target", include_in_analysis=True)
    db.add_all([epic_a, epic_b])
    db.commit()

    item_a = BacklogItem(id=str(uuid.uuid4()), issue_id="pka", title="Alpha")
    item_b = BacklogItem(id=str(uuid.uuid4()), issue_id="pkb", title="Beta")
    db.add_all([item_a, item_b])
    db.commit()

    scenario_a = PlanningScenario(id=str(uuid.uuid4()), name="SA", year=2026, quarter="Q3",
                                   status="approved", team="TeamA")
    scenario_b = PlanningScenario(id=str(uuid.uuid4()), name="SB", year=2026, quarter="Q3",
                                   status="approved", team="TeamB")
    db.add_all([scenario_a, scenario_b])
    db.commit()

    db.add_all([
        ScenarioAllocation(id=str(uuid.uuid4()), scenario_id=scenario_a.id,
                            backlog_item_id=item_a.id, included_flag=True),
        ScenarioAllocation(id=str(uuid.uuid4()), scenario_id=scenario_b.id,
                            backlog_item_id=item_b.id, included_flag=True),
    ])
    db.commit()

    svc = ProjectsService(db)
    combos = [
        {},
        {"team_filter": ["TeamA"]},
        {"team_filter": ["TeamB"]},
        {"team_filter": ["TeamA", "TeamB"]},
        {"category": "archive_target"},
        {"status_category": "done"},
        {"search": "Alpha"},
        {"team_filter": ["TeamB"], "category": "archive_target"},
        {"team_filter": ["TeamA"], "category": "archive_target"},  # пересечение пусто
    ]
    for extra in combos:
        expected = {i.key for i in svc.list_projects(year=2026, quarter=3, **extra)}
        actual = set(svc.list_project_keys(year=2026, quarter=3, **extra))
        assert actual == expected, f"mismatch for filters {extra}"

    # Другой квартал — пусто с обеих сторон (нет подходящего сценария).
    assert svc.list_project_keys(year=2026, quarter=4) == []
    assert svc.list_projects(year=2026, quarter=4) == []


def test_list_project_keys_falls_back_to_list_projects_without_quarter(db_session):
    """Без year/quarter лёгкого пути нет: команда фильтруется постфактум по
    авторам списаний, значит list_project_keys обязан честно делегировать
    в list_projects, а не пытаться угадать по одному запросу корней."""
    db = db_session
    _make_project(db, "pk2", "PK2")
    parent = Issue(id="pk2root", jira_issue_id="910", key="PK2-1", summary="No quarter",
                   issue_type="Epic", status="Done", project_id="pk2",
                   category="quarterly_tasks", include_in_analysis=True)
    child = Issue(id="pk2child", jira_issue_id="911", key="PK2-2", summary="Child",
                  issue_type="Task", status="Done", project_id="pk2",
                  parent_id="pk2root", category="tech_debt", include_in_analysis=True)
    emp = Employee(id="pk2emp", jira_account_id="pk2emp", display_name="E",
                   email="e@e", is_active=True, team="TeamQ")
    db.add_all([parent, child, emp])
    db.commit()
    db.add(Worklog(id="pk2w", jira_worklog_id="pk2w", issue_id="pk2child",
                   employee_id="pk2emp", hours=5.0, time_spent_seconds=18000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.commit()

    svc = ProjectsService(db)
    for extra in ({}, {"team_filter": ["TeamQ"]}, {"team_filter": ["Nope"]}):
        expected = {i.key for i in svc.list_projects(**extra)}
        actual = set(svc.list_project_keys(**extra))
        assert actual == expected, f"mismatch for filters {extra}"


def test_list_project_keys_falls_back_when_only_one_of_year_quarter_given(db_session):
    """Если задан только год или только квартал — list_projects всё равно
    считает это «без квартала» (её условие для worklog-фильтра команды —
    ``year is None or quarter is None``, не оба сразу). Проверяем этот
    случай отдельно от полностью пустого: проверка «оба отсутствуют» вместо
    «хотя бы один отсутствует» дала бы расхождение именно здесь.
    """
    db = db_session
    _make_project(db, "pk3", "PK3")
    root_x = Issue(id="pk3x", jira_issue_id="920", key="PK3-1", summary="X",
                   issue_type="Epic", status="Done", project_id="pk3",
                   category="quarterly_tasks", include_in_analysis=True)
    child_x = Issue(id="pk3xc", jira_issue_id="921", key="PK3-1C", summary="Xc",
                    issue_type="Task", status="Done", project_id="pk3",
                    parent_id="pk3x", category="tech_debt", include_in_analysis=True)
    root_y = Issue(id="pk3y", jira_issue_id="922", key="PK3-2", summary="Y",
                   issue_type="Epic", status="Done", project_id="pk3",
                   category="quarterly_tasks", include_in_analysis=True)
    child_y = Issue(id="pk3yc", jira_issue_id="923", key="PK3-2C", summary="Yc",
                    issue_type="Task", status="Done", project_id="pk3",
                    parent_id="pk3y", category="tech_debt", include_in_analysis=True)
    emp_q = Employee(id="pk3empq", jira_account_id="pk3empq", display_name="Q",
                      email="q@e", is_active=True, team="TeamQ")
    emp_o = Employee(id="pk3empo", jira_account_id="pk3empo", display_name="O",
                      email="o@e", is_active=True, team="OtherTeam")
    db.add_all([root_x, child_x, root_y, child_y, emp_q, emp_o])
    db.commit()
    db.add_all([
        EmployeeTeam(id="pk3etq", employee_id="pk3empq", team="TeamQ", is_primary=True),
        EmployeeTeam(id="pk3eto", employee_id="pk3empo", team="OtherTeam", is_primary=True),
    ])
    db.commit()
    db.add(Worklog(id="pk3wx", jira_worklog_id="pk3wx", issue_id="pk3xc",
                   employee_id="pk3empq", hours=5.0, time_spent_seconds=18000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.add(Worklog(id="pk3wy", jira_worklog_id="pk3wy", issue_id="pk3yc",
                   employee_id="pk3empo", hours=5.0, time_spent_seconds=18000,
                   started_at=datetime(2026, 2, 1), updated_at=datetime(2026, 2, 1)))
    db.commit()

    svc = ProjectsService(db)
    for partial in ({"year": 2026}, {"quarter": 3}):
        expected = {i.key for i in svc.list_projects(team_filter=["TeamQ"], **partial)}
        actual = set(svc.list_project_keys(team_filter=["TeamQ"], **partial))
        assert actual == expected, f"mismatch for partial args {partial}"
        assert expected == {"PK3-1"}, "sanity: только PK3-1 списан TeamQ"


def test_detail_team_label_is_team_on_worklog_day(db_session):
    """Подпись команды — та, где человек был в день последнего списания."""
    from datetime import date

    db = db_session
    _make_category(db, "tech_debt", "Tech Debt", "#00c9c8")
    _make_project(db, "p9", "PRJ9")
    parent = Issue(id="ip9", jira_issue_id="900", key="PRJ9-900", summary="Big",
                   issue_type="Epic", status="Done", project_id="p9",
                   category="quarterly_tasks", include_in_analysis=True)
    child = Issue(id="ic9", jira_issue_id="901", key="PRJ9-901", summary="Sub",
                  issue_type="Task", status="Done", project_id="p9",
                  parent_id="ip9", category="tech_debt", include_in_analysis=True)
    emp = Employee(id="e_m", jira_account_id="am", display_name="Moved",
                   email="m@e", is_active=True, team="NewTeam")
    db.add_all([parent, child, emp])
    db.commit()
    db.add_all([
        EmployeeTeam(id="et_old", employee_id="e_m", team="OldTeam",
                     is_primary=False, left_at=date(2026, 3, 1)),
        EmployeeTeam(id="et_new", employee_id="e_m", team="NewTeam",
                     is_primary=True, joined_at=date(2026, 3, 1)),
    ])
    db.add(Worklog(id="wm", jira_worklog_id="wm", issue_id="ic9", employee_id="e_m",
                   hours=8, time_spent_seconds=28800,
                   started_at=datetime(2026, 2, 10), updated_at=datetime(2026, 2, 10)))
    db.commit()

    detail = ProjectsService(db).get_project_detail("PRJ9-900")
    assert detail.employees[0].team == "OldTeam"
