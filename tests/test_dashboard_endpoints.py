# tests/test_dashboard_endpoints.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_projects_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    # Counters
    assert "total" in data
    assert "done" in data
    assert "in_progress" in data
    assert "overdue" in data
    assert "not_started" in data
    # KPI top-level
    assert "total_fact_hours" in data
    assert "total_plan_hours" in data
    assert "avg_load_pct" in data
    assert "silent_count" in data
    assert "forecast_done" in data
    assert "forecast_pct" in data
    # Per-project list
    assert "projects" in data
    assert isinstance(data["projects"], list)
    # Удалённые поля больше НЕ должны быть в ответе
    assert "attention_list" not in data
    assert "overrun_list" not in data


def test_projects_widget_project_item_shape():
    """При наличии проектов в списке проверяем форму одного элемента."""
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=2")
    data = resp.json()
    if data["projects"]:
        p = data["projects"][0]
        for key in [
            "issue_key", "title", "status_category",
            "plan_hours", "fact_hours", "delta_hours",
            "subtasks_done", "subtasks_total",
            "assignees", "assignees_total",
            "due_date", "days_to_due",
            "trend_hours_week", "trend_dir",
            "forecast_close_date", "forecast_in_quarter",
            "silent_days", "weekly_activity",
        ]:
            assert key in p, f"missing key: {key}"
        assert isinstance(p["assignees"], list)
        assert isinstance(p["weekly_activity"], list)
        assert p["trend_dir"] in ("up", "down", "flat")


def test_projects_widget_invalid_quarter():
    resp = client.get("/api/v1/analytics/dashboard/projects?year=2026&quarter=5")
    assert resp.status_code == 422


def test_norm_work_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "roles" in data
    assert "total_plan" in data
    assert "total_fact" in data
    assert "total_pct" in data
    assert isinstance(data["roles"], list)
    assert "items" not in data


def test_norm_work_widget_role_shape():
    resp = client.get("/api/v1/analytics/dashboard/norm-work?year=2026&quarter=2")
    data = resp.json()
    if data["roles"]:
        role = data["roles"][0]
        for k in [
            "role_code", "role_label", "role_color", "employees_count",
            "total_plan", "total_fact", "total_pct", "employees",
        ]:
            assert k in role
        assert isinstance(role["employees"], list)
        if role["employees"]:
            emp = role["employees"][0]
            for k in [
                "employee_id", "name", "initials",
                "plan_hours", "fact_hours", "pct", "work_types",
            ]:
                assert k in emp
            if emp["work_types"]:
                wt = emp["work_types"][0]
                for k in ["work_type_id", "label", "plan_hours", "fact_hours", "pct"]:
                    assert k in wt


def test_categories_widget_returns_200():
    resp = client.get("/api/v1/analytics/dashboard/categories?year=2026&quarter=2")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total_hours" in data
    assert "employees" in data
    assert isinstance(data["employees"], list)
    for item in data["items"]:
        assert "key" in item
        assert "hours" in item
        assert "worklog_count" in item
        assert "employee_count" in item
        assert "avg_worklog_minutes" in item
        assert "pct" in item
    for emp in data["employees"]:
        for k in ["employee_id", "name", "initials", "last_worklog_at", "days_since_last"]:
            assert k in emp


def test_dashboard_projects_splits_team_alien(testclient_db_session):
    """Виджет делит часы на командные и чужие; загрузка считается от команды."""
    from datetime import datetime
    from uuid import uuid4
    from app.main import app
    from app.database import get_db
    from fastapi.testclient import TestClient
    from app.models import (Project, Issue, Worklog, Employee, EmployeeTeam,
                            BacklogItem, PlanningScenario, ScenarioAllocation, Category)

    db = testclient_db_session

    # seed Category
    cat = db.query(Category).filter_by(code="quarterly_tasks").first()
    if not cat:
        db.add(Category(id=str(uuid4()), code="quarterly_tasks",
                        label="Квартальные задачи", color="#2dd4bf"))

    # Project + Epic
    project = Project(id=str(uuid4()), jira_project_id="jp1", key="TST",
                      name="Test project", is_active=True)
    db.add(project)

    rfa_id = str(uuid4())
    rfa = Issue(id=rfa_id, jira_issue_id="ji1", key="TST-1", summary="Test RFA",
                issue_type="Инициатива", status="In Progress",
                status_category="indeterminate", project_id=project.id,
                category="quarterly_tasks")
    db.add(rfa)

    team = "Команда Тест"
    epic_id = str(uuid4())
    epic = Issue(id=epic_id, jira_issue_id="ji1e", key="TST-2", summary="Test epic",
                 issue_type="Epic", status="In Progress",
                 status_category="indeterminate", project_id=project.id,
                 parent_id=rfa_id, team=team, category="quarterly_tasks")
    db.add(epic)

    # BacklogItem + Scenario + Allocation
    bi = BacklogItem(id=str(uuid4()), title="Test RFA", issue_id=rfa_id,
                    estimate_analyst_hours=100.0)
    db.add(bi)

    scn = PlanningScenario(id=str(uuid4()), name="Q2 2026 plan", year=2026,
                           quarter="Q2", team=team, status="approved")
    db.add(scn)
    db.flush()

    db.add(ScenarioAllocation(id=str(uuid4()), scenario_id=scn.id,
                              backlog_item_id=bi.id, included_flag=True,
                              planned_hours=100.0))

    # Двое сотрудников: один в команде, один вне
    own = Employee(id=str(uuid4()), jira_account_id="acc1",
                   display_name="Свой Иван", is_active=True)
    alien = Employee(id=str(uuid4()), jira_account_id="acc2",
                     display_name="Чужой Орлов", is_active=True)
    db.add_all([own, alien])
    db.add(EmployeeTeam(id=str(uuid4()), employee_id=own.id,
                        team=team, is_primary=True))

    # Worklogs: 10ч свой + 5ч чужой
    started = datetime(2026, 4, 15, 10, 0, 0)
    db.add_all([
        Worklog(id=str(uuid4()), jira_worklog_id="wl1", issue_id=epic_id,
                employee_id=own.id, started_at=started,
                time_spent_seconds=10*3600, hours=10.0),
        Worklog(id=str(uuid4()), jira_worklog_id="wl2", issue_id=epic_id,
                employee_id=alien.id, started_at=started,
                time_spent_seconds=5*3600, hours=5.0),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["total_team_fact_hours"] == 10.0, data
        assert data["total_alien_fact_hours"] == 5.0, data
        assert data["alien_helper_count"] == 1
        assert data["alien_projects_count"] == 1

        assert len(data["projects"]) == 1, data
        project_item = data["projects"][0]
        assert project_item["team_fact_hours"] == 10.0
        assert project_item["alien_fact_hours"] == 5.0
        assert project_item["alien_helper_count"] == 1
        assert len(project_item["alien_helpers"]) == 1
        assert project_item["alien_helpers"][0]["initials"] == "ЧО"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dashboard_projects_team_with_no_members_marks_all_as_alien(testclient_db_session):
    """Команда задана но без сотрудников — все ворклоги считаются чужими."""
    from datetime import datetime
    from uuid import uuid4
    from app.main import app
    from app.database import get_db
    from fastapi.testclient import TestClient
    from app.models import (Project, Issue, Worklog, Employee,
                            BacklogItem, PlanningScenario, ScenarioAllocation, Category)

    db = testclient_db_session

    cat = db.query(Category).filter_by(code="quarterly_tasks").first()
    if not cat:
        db.add(Category(id=str(uuid4()), code="quarterly_tasks",
                        label="Квартальные задачи", color="#2dd4bf"))

    project = Project(id=str(uuid4()), jira_project_id="jp_no_team", key="NTM",
                      name="No-team project", is_active=True)
    db.add(project)

    team_without_members = "Пустая команда"

    rfa_id = str(uuid4())
    rfa = Issue(id=rfa_id, jira_issue_id="ji_no_team", key="NTM-1",
                summary="RFA without team members",
                issue_type="Инициатива", status="In Progress",
                status_category="indeterminate", project_id=project.id,
                category="quarterly_tasks")
    db.add(rfa)

    epic_id = str(uuid4())
    epic = Issue(id=epic_id, jira_issue_id="ji_no_team_e", key="NTM-2",
                 summary="Epic without team members",
                 issue_type="Epic", status="In Progress",
                 status_category="indeterminate", project_id=project.id,
                 parent_id=rfa_id, team=team_without_members,
                 category="quarterly_tasks")
    db.add(epic)

    bi = BacklogItem(id=str(uuid4()), title="RFA without team members",
                    issue_id=rfa_id, estimate_analyst_hours=50.0)
    db.add(bi)
    scn = PlanningScenario(id=str(uuid4()), name="Q2 2026", year=2026,
                           quarter="Q2", team=team_without_members, status="approved")
    db.add(scn)
    db.flush()

    db.add(ScenarioAllocation(id=str(uuid4()), scenario_id=scn.id,
                              backlog_item_id=bi.id, included_flag=True,
                              planned_hours=50.0))

    # Сотрудник не сопоставлен с этой командой (нет EmployeeTeam)
    helper = Employee(id=str(uuid4()), jira_account_id="acc_helper",
                      display_name="Помощник Один", is_active=True)
    db.add(helper)

    db.add(Worklog(id=str(uuid4()), jira_worklog_id="wl_help_1",
                  issue_id=epic_id, employee_id=helper.id,
                  started_at=datetime(2026, 4, 15, 10, 0, 0),
                  time_spent_seconds=8*3600, hours=8.0))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(
            f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team_without_members}"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["total_team_fact_hours"] == 0.0, data
        assert data["total_alien_fact_hours"] == 8.0, data
        assert data["alien_helper_count"] == 1
        assert data["alien_projects_count"] == 1

        assert len(data["projects"]) == 1, data
        project_item = data["projects"][0]
        assert project_item["team_fact_hours"] == 0.0
        assert project_item["alien_fact_hours"] == 8.0
        assert project_item["alien_helper_count"] == 1
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dashboard_projects_alien_helpers_top3(testclient_db_session):
    """В alien_helpers возвращается только top-3 по часам, но count полный."""
    from datetime import datetime
    from uuid import uuid4
    from app.main import app
    from app.database import get_db
    from fastapi.testclient import TestClient
    from app.models import (Project, Issue, Worklog, Employee,
                            BacklogItem, PlanningScenario, ScenarioAllocation, Category)

    db = testclient_db_session

    cat = db.query(Category).filter_by(code="quarterly_tasks").first()
    if not cat:
        db.add(Category(id=str(uuid4()), code="quarterly_tasks",
                        label="Квартальные задачи", color="#2dd4bf"))

    project = Project(id=str(uuid4()), jira_project_id="jp_top3", key="TP3",
                      name="Top-3 test project", is_active=True)
    db.add(project)

    team = "Команда Топ3"

    rfa_id = str(uuid4())
    rfa = Issue(id=rfa_id, jira_issue_id="ji_top3", key="TP3-1",
                summary="Top-3 RFA", issue_type="Инициатива", status="In Progress",
                status_category="indeterminate", project_id=project.id,
                category="quarterly_tasks")
    db.add(rfa)

    epic_id = str(uuid4())
    epic = Issue(id=epic_id, jira_issue_id="ji_top3_e", key="TP3-2",
                 summary="Top-3 epic", issue_type="Epic", status="In Progress",
                 status_category="indeterminate", project_id=project.id,
                 parent_id=rfa_id, team=team, category="quarterly_tasks")
    db.add(epic)

    bi = BacklogItem(id=str(uuid4()), title="Top-3 RFA",
                    issue_id=rfa_id, estimate_analyst_hours=100.0)
    db.add(bi)
    scn = PlanningScenario(id=str(uuid4()), name="Q2 2026 top3", year=2026,
                           quarter="Q2", team=team, status="approved")
    db.add(scn)
    db.flush()
    db.add(ScenarioAllocation(id=str(uuid4()), scenario_id=scn.id,
                              backlog_item_id=bi.id, included_flag=True,
                              planned_hours=100.0))

    started = datetime(2026, 4, 15, 10, 0, 0)

    # 5 чужих с разными часами — никто в команде
    hours_by_name = [("А А", 10), ("Б Б", 8), ("В В", 6), ("Г Г", 4), ("Д Д", 2)]
    for idx, (name, h) in enumerate(hours_by_name):
        emp = Employee(id=str(uuid4()), jira_account_id=f"acc_top3_{idx}",
                       display_name=name, is_active=True)
        db.add(emp)
        db.add(Worklog(id=str(uuid4()), jira_worklog_id=f"wl_top3_{idx}",
                       issue_id=epic_id, employee_id=emp.id,
                       started_at=started, time_spent_seconds=h*3600,
                       hours=float(h)))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
        assert resp.status_code == 200, resp.text
        project_item = resp.json()["projects"][0]
        assert project_item["alien_helper_count"] == 5
        assert len(project_item["alien_helpers"]) == 3
        assert [h["initials"] for h in project_item["alien_helpers"]] == ["АА", "ББ", "ВВ"]
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_rfa_with_tree(db, *, team, rfa_status="indeterminate"):
    """Создаёт Инициативу (RFA) с привязкой к утверждённому сценарию.

    Возвращает (rfa_id, scenario, backlog_item, project) — задачи/эпики
    докидывает вызывающий тест.
    """
    from uuid import uuid4
    from app.models import (Project, Issue, BacklogItem, PlanningScenario,
                            ScenarioAllocation, Category)

    cat = db.query(Category).filter_by(code="quarterly_tasks").first()
    if not cat:
        db.add(Category(id=str(uuid4()), code="quarterly_tasks",
                        label="Квартальные задачи", color="#2dd4bf"))

    project = Project(id=str(uuid4()), jira_project_id=f"jp_{uuid4().hex[:6]}",
                      key=f"P{uuid4().hex[:3].upper()}", name="Tree project",
                      is_active=True)
    db.add(project)

    rfa_id = str(uuid4())
    rfa = Issue(id=rfa_id, jira_issue_id=f"ji_{uuid4().hex[:6]}",
                key=f"RFA-{uuid4().hex[:4]}", summary="Инициатива",
                issue_type="Инициатива", status="In Progress",
                status_category=rfa_status, project_id=project.id)
    db.add(rfa)

    bi = BacklogItem(id=str(uuid4()), title="Инициатива", issue_id=rfa_id,
                    estimate_analyst_hours=100.0)
    db.add(bi)

    scn = PlanningScenario(id=str(uuid4()), name="Q2 2026", year=2026,
                           quarter="Q2", team=team, status="approved")
    db.add(scn)
    db.flush()
    db.add(ScenarioAllocation(id=str(uuid4()), scenario_id=scn.id,
                              backlog_item_id=bi.id, included_flag=True,
                              planned_hours=100.0))
    return rfa_id, scn, bi, project


def test_dashboard_projects_cascades_into_deep_subtree(testclient_db_session):
    """Часы на подзадаче глубоко под эпиком команды попадают в факт Инициативы."""
    from datetime import datetime
    from uuid import uuid4
    from app.database import get_db
    from app.models import Issue, Worklog, Employee, EmployeeTeam

    db = testclient_db_session
    team = "Команда Каскад"
    rfa_id, scn, bi, project = _seed_rfa_with_tree(db, team=team)

    # RFA → Эпик(команда) → Задача → Подзадача
    epic_id, task_id, sub_id = str(uuid4()), str(uuid4()), str(uuid4())
    db.add_all([
        Issue(id=epic_id, jira_issue_id="e1", key="PRJ-1", summary="Эпик",
              issue_type="Epic", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=rfa_id, team=team),
        Issue(id=task_id, jira_issue_id="t1", key="PRJ-2", summary="Задача",
              issue_type="Task", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=epic_id),
        Issue(id=sub_id, jira_issue_id="s1", key="PRJ-3", summary="Подзадача",
              issue_type="Sub-task", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=task_id),
    ])

    own = Employee(id=str(uuid4()), jira_account_id="acc_casc",
                   display_name="Свой Иван", is_active=True)
    db.add(own)
    db.add(EmployeeTeam(id=str(uuid4()), employee_id=own.id, team=team, is_primary=True))

    # Ворклог 12ч на самой глубокой подзадаче
    db.add(Worklog(id=str(uuid4()), jira_worklog_id="wl_casc", issue_id=sub_id,
                   employee_id=own.id, started_at=datetime(2026, 4, 15, 10, 0, 0),
                   time_spent_seconds=12*3600, hours=12.0))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data["projects"]) == 1, data
        item = data["projects"][0]
        assert item["fact_hours"] == 12.0, item
        assert item["team_fact_hours"] == 12.0, item
        assert item["alien_fact_hours"] == 0.0, item
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dashboard_projects_excludes_foreign_team_epic(testclient_db_session):
    """Эпик чужой команды под той же Инициативой в виджет не попадает вовсе."""
    from datetime import datetime
    from uuid import uuid4
    from app.database import get_db
    from app.models import Issue, Worklog, Employee, EmployeeTeam

    db = testclient_db_session
    team_a = "Команда А"
    team_b = "Команда Б"
    rfa_id, scn, bi, project = _seed_rfa_with_tree(db, team=team_a)

    # Под RFA два эпика: A и B; в каждом по задаче с ворклогом
    epic_a, task_a = str(uuid4()), str(uuid4())
    epic_b, task_b = str(uuid4()), str(uuid4())
    db.add_all([
        Issue(id=epic_a, jira_issue_id="ea", key="PRJ-A", summary="Эпик А",
              issue_type="Epic", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=rfa_id, team=team_a),
        Issue(id=task_a, jira_issue_id="ta", key="PRJ-A2", summary="Задача А",
              issue_type="Task", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=epic_a),
        Issue(id=epic_b, jira_issue_id="eb", key="PRJ-B", summary="Эпик Б",
              issue_type="Epic", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=rfa_id, team=team_b),
        Issue(id=task_b, jira_issue_id="tb", key="PRJ-B2", summary="Задача Б",
              issue_type="Task", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=epic_b),
    ])

    emp_a = Employee(id=str(uuid4()), jira_account_id="acc_a",
                     display_name="Алла А", is_active=True)
    emp_b = Employee(id=str(uuid4()), jira_account_id="acc_b",
                     display_name="Борис Б", is_active=True)
    db.add_all([emp_a, emp_b])
    db.add_all([
        EmployeeTeam(id=str(uuid4()), employee_id=emp_a.id, team=team_a, is_primary=True),
        EmployeeTeam(id=str(uuid4()), employee_id=emp_b.id, team=team_b, is_primary=True),
    ])
    started = datetime(2026, 4, 15, 10, 0, 0)
    db.add_all([
        Worklog(id=str(uuid4()), jira_worklog_id="wl_a", issue_id=task_a,
                employee_id=emp_a.id, started_at=started, time_spent_seconds=6*3600, hours=6.0),
        Worklog(id=str(uuid4()), jira_worklog_id="wl_b", issue_id=task_b,
                employee_id=emp_b.id, started_at=started, time_spent_seconds=9*3600, hours=9.0),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team_a}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        item = data["projects"][0]
        # Только дерево эпика A; эпик B исключён целиком
        assert item["fact_hours"] == 6.0, item
        assert item["team_fact_hours"] == 6.0, item
        assert item["alien_fact_hours"] == 0.0, item
        assert data["total_fact_hours"] == 6.0, data
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dashboard_projects_alien_help_inside_team_epic(testclient_db_session):
    """Часы не-командного сотрудника на задаче внутри командного эпика → помощь извне."""
    from datetime import datetime
    from uuid import uuid4
    from app.database import get_db
    from app.models import Issue, Worklog, Employee, EmployeeTeam

    db = testclient_db_session
    team = "Команда Помощь"
    rfa_id, scn, bi, project = _seed_rfa_with_tree(db, team=team)

    epic_id, task_id = str(uuid4()), str(uuid4())
    db.add_all([
        Issue(id=epic_id, jira_issue_id="ep", key="PRJ-H1", summary="Эпик",
              issue_type="Epic", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=rfa_id, team=team),
        Issue(id=task_id, jira_issue_id="tp", key="PRJ-H2", summary="Задача",
              issue_type="Task", status="In Progress", status_category="indeterminate",
              project_id=project.id, parent_id=epic_id),
    ])
    own = Employee(id=str(uuid4()), jira_account_id="acc_own_h",
                   display_name="Свой Иван", is_active=True)
    alien = Employee(id=str(uuid4()), jira_account_id="acc_alien_h",
                     display_name="Чужой Орлов", is_active=True)
    db.add_all([own, alien])
    db.add(EmployeeTeam(id=str(uuid4()), employee_id=own.id, team=team, is_primary=True))
    started = datetime(2026, 4, 15, 10, 0, 0)
    db.add_all([
        Worklog(id=str(uuid4()), jira_worklog_id="wl_own_h", issue_id=task_id,
                employee_id=own.id, started_at=started, time_spent_seconds=10*3600, hours=10.0),
        Worklog(id=str(uuid4()), jira_worklog_id="wl_alien_h", issue_id=task_id,
                employee_id=alien.id, started_at=started, time_spent_seconds=4*3600, hours=4.0),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
        assert resp.status_code == 200, resp.text
        item = resp.json()["projects"][0]
        assert item["team_fact_hours"] == 10.0, item
        assert item["alien_fact_hours"] == 4.0, item
        assert item["alien_helper_count"] == 1, item
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dashboard_projects_qa_role_counts_as_team(testclient_db_session):
    """Сотрудник с ролью qa — общий ресурс, не «помощь», даже если не сопоставлен с командой."""
    from datetime import datetime
    from uuid import uuid4
    from app.main import app
    from app.database import get_db
    from fastapi.testclient import TestClient
    from app.models import (Project, Issue, Worklog, Employee, EmployeeTeam,
                            BacklogItem, PlanningScenario, ScenarioAllocation, Category)

    db = testclient_db_session

    cat = db.query(Category).filter_by(code="quarterly_tasks").first()
    if not cat:
        db.add(Category(id=str(uuid4()), code="quarterly_tasks",
                        label="Квартальные задачи", color="#2dd4bf"))

    project = Project(id=str(uuid4()), jira_project_id="jp_qa", key="QAT",
                      name="QA test project", is_active=True)
    db.add(project)

    team = "Команда QA-тест"

    rfa_id = str(uuid4())
    rfa = Issue(id=rfa_id, jira_issue_id="ji_qa", key="QAT-1",
                summary="RFA with QA help", issue_type="Инициатива", status="In Progress",
                status_category="indeterminate", project_id=project.id,
                category="quarterly_tasks")
    db.add(rfa)

    epic_id = str(uuid4())
    epic = Issue(id=epic_id, jira_issue_id="ji_qa_e", key="QAT-2",
                 summary="Epic with QA help", issue_type="Epic", status="In Progress",
                 status_category="indeterminate", project_id=project.id,
                 parent_id=rfa_id, team=team, category="quarterly_tasks")
    db.add(epic)

    bi = BacklogItem(id=str(uuid4()), title="QA RFA",
                    issue_id=rfa_id, estimate_analyst_hours=50.0)
    db.add(bi)
    scn = PlanningScenario(id=str(uuid4()), name="Q2 2026 QA", year=2026,
                           quarter="Q2", team=team, status="approved")
    db.add(scn)
    db.flush()
    db.add(ScenarioAllocation(id=str(uuid4()), scenario_id=scn.id,
                              backlog_item_id=bi.id, included_flag=True,
                              planned_hours=50.0))

    # Один член команды (без роли) + один QA не сопоставлен с командой
    own = Employee(id=str(uuid4()), jira_account_id="acc_qa_own",
                   display_name="Свой Иван", is_active=True)
    qa = Employee(id=str(uuid4()), jira_account_id="acc_qa_shared",
                  display_name="QA Шевелёв", is_active=True, role="qa")
    db.add_all([own, qa])
    db.add(EmployeeTeam(id=str(uuid4()), employee_id=own.id, team=team, is_primary=True))

    started = datetime(2026, 4, 15, 10, 0, 0)
    db.add_all([
        Worklog(id=str(uuid4()), jira_worklog_id="wl_qa_own", issue_id=epic_id,
                employee_id=own.id, started_at=started,
                time_spent_seconds=10*3600, hours=10.0),
        Worklog(id=str(uuid4()), jira_worklog_id="wl_qa_shared", issue_id=epic_id,
                employee_id=qa.id, started_at=started,
                time_spent_seconds=4*3600, hours=4.0),
    ])
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        c = TestClient(app)
        resp = c.get(f"/api/v1/analytics/dashboard/projects?year=2026&quarter=2&teams={team}")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # QA шевелёв должен попасть в команду, не в чужих
        assert data["total_team_fact_hours"] == 14.0, data
        assert data["total_alien_fact_hours"] == 0.0, data
        assert data["alien_helper_count"] == 0
        assert data["alien_projects_count"] == 0
    finally:
        app.dependency_overrides.pop(get_db, None)
