"""Разработчик из колонки сценария получает разработку; один человек — одна фаза."""

from sqlalchemy import select

from app.models import BacklogItem, PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan
from tests.services.test_rp_scenario_executor import _weekdays


def _item(db, dev=10.0, analyst=8.0, assignee=None, developer=None, manual=False):
    it = BacklogItem(
        title="x", priority=1, estimate_dev_hours=dev, estimate_analyst_hours=analyst,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
        assignee_manual=manual,
        developer_employee_id=developer.id if developer else None,
    )
    db.add(it)
    db.flush()
    return it


def test_developer_column_takes_dev_over_jira_and_capacity(db_session):
    dev_col = make_employee(db_session, "Из колонки", "B")
    jira_dev = make_employee(db_session, "Из Jira", "B")
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    item = _item(db_session, developer=dev_col)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [dev_col, jira_dev, an],
        jira_dev={item.id: jira_dev.id},
        capacity={dev_col.id: 0.0},  # ёмкости нет — всё равно он
    )

    assert res["dev"][item.id] == dev_col.id
    assert res["analyst"][item.id] == an.id


def test_developer_role_executor_goes_to_analysis_when_column_set(db_session):
    """Колонка заполнена: исполнитель строки — на анализ, какая бы ни была роль."""
    executor = make_employee(db_session, "Исполнитель-разработчик", "B")  # роль dev по умолчанию
    dev_col = make_employee(db_session, "Из колонки", "B")
    item = _item(db_session, assignee=executor, developer=dev_col)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [executor, dev_col])

    assert res["analyst"][item.id] == executor.id
    assert res["dev"][item.id] == dev_col.id


def test_same_person_in_both_columns_takes_only_dev(db_session):
    same = make_employee(db_session, "Один", "B", role="analyst")
    an = make_employee(db_session, "Другой аналитик", "B", role="analyst")
    item = _item(db_session, assignee=same, developer=same)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [same, an])

    assert res["dev"][item.id] == same.id
    assert res["analyst"][item.id] == an.id


def test_greedy_analyst_skips_row_developer(db_session):
    only_an = make_employee(db_session, "Единственный аналитик", "B", role="analyst")
    item = _item(db_session, developer=only_an)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [only_an])

    assert res["dev"][item.id] == only_an.id
    assert res["analyst"][item.id] is None


def test_empty_column_keeps_old_behaviour(db_session):
    executor = make_employee(db_session, "Исполнитель-разработчик", "B")
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    item = _item(db_session, assignee=executor)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [executor, an])

    assert res["dev"][item.id] == executor.id
    assert res["analyst"][item.id] == an.id


def test_busy_developer_from_other_team_is_borrowed_and_reported(db_session):
    make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Шутов", "A")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=1), ext,
         _weekdays("2026-01-01", "2026-04-30"))
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12)
    item.developer_employee_id = ext.id
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = db_session.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_b.id, ResourcePlanAssignment.phase == "dev"
        )
    ).scalars().all()
    assert rows == []
    [c] = db_session.execute(
        select(PlanConflict).where(
            PlanConflict.plan_id == plan_b.id, PlanConflict.type == "UNPLACED_HOURS"
        )
    ).scalars().all()
    assert c.backlog_item_id == item.id
    assert c.employee_id == ext.id


def test_leveler_may_not_reassign_column_developer(db_session, monkeypatch):
    """Разработку у разработчика из колонки выравниватель не отдаёт коллеге:
    расчёт плана передаёт его фазы как заблокированные."""
    from app.services.rcpsp_leveler import RcpspLeveler

    dev_col = make_employee(db_session, "Из колонки", "B")
    make_employee(db_session, "Коллега", "B")
    sc, plan = make_plan(db_session, "B", plan_status="draft")
    with_col = add_item(db_session, sc, "С разработчиком", dev=8)
    with_col.developer_employee_id = dev_col.id
    add_item(db_session, sc, "Без разработчика", dev=8, priority=2)
    db_session.commit()

    seen = {}
    original = RcpspLeveler.level

    def _spy(self, *args, **kwargs):
        seen["locked"] = kwargs.get("locked")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RcpspLeveler, "level", _spy)
    ResourcePlanningService(db_session).compute_schedule(plan.id)

    assert seen["locked"] == {(with_col.id, "dev"): dev_col.id}
