"""Минорные изменения: сводка по командам для «Целевых задач»."""

from app.models import Category, Issue, MandatoryWorkType, Project, ScenarioRule
from app.services import minor_changes as mc
from tests.services.normed_factory import _types
from tests.services.xteam_factory import make_employee, make_plan

TEAM = "Команда 1С"
Q = (2026, 1)


def _setup(db):
    """Виды работ + категория «minor_change» с видом «Минорные изменения»."""
    types = _types(db)
    db.add(Category(code="minor_change", label="Минорные", work_type_id=types["minor_change"].id))
    db.add(Category(code="quarterly_tasks", label="Квартальные", work_type_id=types["organizational"].id))
    project = Project(jira_project_id="p1", key="OS", name="OS")
    db.add(project)
    db.flush()
    return types, project


def _issue(db, project, key, parent=None, team=TEAM, status="В работе", cat=None, **kw):
    kw.setdefault("status_category", "indeterminate")
    i = Issue(
        jira_issue_id=f"j-{key}", key=key, summary=f"Задача {key}", issue_type=kw.pop("issue_type", "Задача"),
        status=status, project_id=project.id, parent_id=parent.id if parent else None,
        team=team, assigned_category=cat, **kw,
    )
    db.add(i)
    db.flush()
    return i


def _block(summary, team=TEAM):
    return next(b for b in summary if b["team"] == team)


def test_category_inherited_from_epic_and_own_category(db_session):
    _t, p = _setup(db_session)
    epic = _issue(db_session, p, "OS-1", issue_type="Эпик", cat="minor_change")
    _issue(db_session, p, "OS-2", parent=epic)                       # наследует от эпика
    _issue(db_session, p, "OS-3", cat="minor_change")                # своя категория
    _issue(db_session, p, "OS-4", cat="quarterly_tasks")             # другая категория
    other = _issue(db_session, p, "OS-5", issue_type="Эпик", cat="quarterly_tasks")
    _issue(db_session, p, "OS-6", parent=other)                      # наследует чужую
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert sorted(t["key"] for t in b["tasks"]) == ["OS-2", "OS-3"]  # эпик с открытым ребёнком — не считаем
    assert b["open_count"] == 2


def test_done_cancelled_and_other_team_excluded(db_session):
    _t, p = _setup(db_session)
    _issue(db_session, p, "OS-1", cat="minor_change")
    _issue(db_session, p, "OS-2", cat="minor_change", status="Готово", status_category="done")
    _issue(db_session, p, "OS-3", cat="minor_change", status="Отменено", status_category="new")
    _issue(db_session, p, "OS-4", cat="minor_change", team="Другая")
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert [t["key"] for t in b["tasks"]] == ["OS-1"]


def test_estimates_by_role_and_unestimated_count(db_session):
    _t, p = _setup(db_session)
    _issue(db_session, p, "OS-1", cat="minor_change", planned_analyst_hours_jira=2, planned_dev_hours_jira=8)
    _issue(db_session, p, "OS-2", cat="minor_change", planned_dev_hours_jira=4, planned_qa_hours_jira=1)
    _issue(db_session, p, "OS-3", cat="minor_change")
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert (b["open_count"], b["estimated_count"], b["unestimated_count"]) == (3, 2, 1)
    assert b["hours"] == {"analyst": 2.0, "dev": 12.0, "qa": 1.0, "opo": 0.0, "total": 15.0}


def test_manual_estimate_wins_like_in_target_tasks(db_session):
    _t, p = _setup(db_session)
    _issue(db_session, p, "OS-1", cat="minor_change", planned_dev_hours_jira=8, planned_dev_hours_manual=3)
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert b["hours"]["dev"] == 3.0


def test_leaves_subtasks_with_estimate_replace_parent(db_session):
    _t, p = _setup(db_session)
    parent = _issue(db_session, p, "OS-1", cat="minor_change", planned_dev_hours_jira=10)
    _issue(db_session, p, "OS-2", parent=parent, issue_type="Подзадача", planned_dev_hours_jira=4)
    _issue(db_session, p, "OS-3", parent=parent, issue_type="Подзадача")
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert sorted(t["key"] for t in b["tasks"]) == ["OS-2", "OS-3"]
    assert (b["open_count"], b["estimated_count"], b["unestimated_count"]) == (2, 1, 1)
    assert b["hours"]["dev"] == 4.0


def test_leaves_parent_estimate_when_children_have_none(db_session):
    _t, p = _setup(db_session)
    parent = _issue(db_session, p, "OS-1", cat="minor_change", planned_dev_hours_jira=10)
    _issue(db_session, p, "OS-2", parent=parent, issue_type="Подзадача")
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert [t["key"] for t in b["tasks"]] == ["OS-1"]
    assert b["hours"]["dev"] == 10.0


def test_leaves_unestimated_parent_is_replaced_by_children(db_session):
    _t, p = _setup(db_session)
    parent = _issue(db_session, p, "OS-1", cat="minor_change")
    _issue(db_session, p, "OS-2", parent=parent, issue_type="Подзадача")
    _issue(db_session, p, "OS-3", parent=parent, issue_type="Подзадача")
    db_session.commit()

    b = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))

    assert sorted(t["key"] for t in b["tasks"]) == ["OS-2", "OS-3"]


def test_task_row_has_epic_assignee_and_roles(db_session):
    _t, p = _setup(db_session)
    epic = _issue(db_session, p, "OS-1", issue_type="Эпик", cat="minor_change", status_category="new")
    _issue(db_session, p, "OS-2", parent=epic, assignee_display_name="Иван", planned_qa_hours_jira=2)
    db_session.commit()

    t = _block(mc.minor_changes_summary(db_session, [TEAM], *Q))["tasks"][0]

    assert (t["key"], t["status"], t["assignee"], t["epic_key"]) == ("OS-2", "В работе", "Иван", "OS-1")
    assert t["epic_summary"] == "Задача OS-1"
    assert t["hours"]["qa"] == 2.0 and t["hours"]["dev"] is None


def test_block_per_requested_team_even_when_empty_and_all_teams_when_not_given(db_session):
    _t, p = _setup(db_session)
    _issue(db_session, p, "OS-1", cat="minor_change", team="А")
    _issue(db_session, p, "OS-2", cat="minor_change", team="Б")
    db_session.commit()

    assert [b["team"] for b in mc.minor_changes_summary(db_session, ["Б", "В"], *Q)] == ["Б", "В"]
    assert _block(mc.minor_changes_summary(db_session, ["Б", "В"], *Q), "В")["open_count"] == 0
    assert sorted(b["team"] for b in mc.minor_changes_summary(db_session, None, *Q)) == ["А", "Б"]


def test_reserve_from_normed_rules_or_none(db_session):
    types, p = _setup(db_session)
    make_employee(db_session, "Разработчик", TEAM, role="dev")
    sc, _plan = make_plan(db_session, TEAM)
    db_session.add(ScenarioRule(scenario_id=sc.id, role="dev", work_type_id=types["minor_change"].id,
                                percent_of_norm=20))
    _issue(db_session, p, "OS-1", cat="minor_change")
    _issue(db_session, p, "OS-2", cat="minor_change", team="Без правил")
    db_session.commit()

    summary = mc.minor_changes_summary(db_session, [TEAM, "Без правил"], *Q)

    assert round(_block(summary)["reserve_hours"], 1) == round(0.2 * 512, 1)
    assert _block(summary, "Без правил")["reserve_hours"] is None


def test_no_minor_category_gives_empty_blocks(db_session):
    db_session.add(MandatoryWorkType(code="project", label="Проекты"))
    db_session.commit()

    assert mc.minor_changes_summary(db_session, [TEAM], *Q) == [
        {"team": TEAM, "open_count": 0, "estimated_count": 0, "unestimated_count": 0,
         "hours": {"analyst": 0.0, "dev": 0.0, "qa": 0.0, "opo": 0.0, "total": 0.0},
         "reserve_hours": None, "tasks": []}
    ]
