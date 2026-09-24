"""Исполнитель строки сценария встаёт на фазу своей роли, в том числе из чужой команды."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models import BacklogItem, PlanConflict, ResourcePlanAssignment
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import add_item, book, make_employee, make_plan


def _item(db, dev=10.0, analyst=0.0, assignee=None, manual=False):
    it = BacklogItem(
        title="x", priority=1, estimate_dev_hours=dev, estimate_analyst_hours=analyst,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
        assignee_manual=manual,
    )
    db.add(it)
    db.flush()
    return it


def _weekdays(start: str, end: str, hours: float = 6.0) -> dict:
    out, d = {}, date.fromisoformat(start)
    while d <= date.fromisoformat(end):
        if d.weekday() < 5:
            out[d.isoformat()] = hours
        d += timedelta(days=1)
    return out


def _rows(db, plan_id, phase):
    return db.execute(
        select(ResourcePlanAssignment).where(
            ResourcePlanAssignment.plan_id == plan_id,
            ResourcePlanAssignment.phase == phase,
        )
    ).scalars().all()


def _conflicts(db, plan_id, type_):
    return db.execute(
        select(PlanConflict).where(PlanConflict.plan_id == plan_id, PlanConflict.type == type_)
    ).scalars().all()


def test_analyst_role_executor_takes_analysis(db_session):
    an = make_employee(db_session, "Аналитик", "B", role="analyst")
    consultant = make_employee(db_session, "Консультант", "B", role="консультант")
    item = _item(db_session, dev=0, analyst=8, assignee=consultant)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees([item], [an, consultant])

    assert res["analyst"][item.id] == consultant.id


def test_executor_without_role_depends_on_analysis_hours(db_session):
    """Роли нет: на анализ, а если у задачи нет часов анализа — на разработку."""
    x = make_employee(db_session, "Без роли", "B", role=None)
    dev = make_employee(db_session, "Разработчик", "B")
    with_analysis = _item(db_session, dev=10, analyst=8, assignee=x)
    no_analysis = _item(db_session, dev=10, analyst=0, assignee=x)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [with_analysis, no_analysis], [x, dev]
    )

    assert res["analyst"][with_analysis.id] == x.id
    assert res["dev"][with_analysis.id] == dev.id
    assert res["dev"][no_analysis.id] == x.id


def test_executor_beats_jira_developer(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _item(db_session, assignee=own)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], jira_dev={item.id: ext.id}, borrowed={ext.id}
    )

    assert res["dev"][item.id] == own.id


def test_manual_executor_from_other_team_is_used(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _item(db_session, assignee=ext, manual=True)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], borrowed={ext.id}
    )

    assert res["dev"][item.id] == ext.id


def test_manual_executor_from_other_team_is_borrowed_in_plan(db_session):
    make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Шутов", "A")
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12, assignee=ext)
    item.assignee_manual = True
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    rows = _rows(db_session, plan_b.id, "dev")
    assert {r.employee_id for r in rows} == {ext.id}
    assert sum(r.hours_allocated or 0 for r in rows) == 12
    assert _conflicts(db_session, plan_b.id, "OUT_OF_TEAM") == []


def test_busy_manual_executor_is_kept_and_reported(db_session):
    """Явный выбор не заменяется при нехватке времени: часы не размещены."""
    make_employee(db_session, "Свой B", "B")
    ext = make_employee(db_session, "Шутов", "A")
    sc_a, plan_a = make_plan(db_session, "A")
    book(db_session, plan_a, add_item(db_session, sc_a, "Работа A", dev=1), ext,
         _weekdays("2026-01-01", "2026-04-30"))
    sc_b, plan_b = make_plan(db_session, "B", plan_status="draft")
    item = add_item(db_session, sc_b, "Работа B", dev=12, assignee=ext)
    item.assignee_manual = True
    db_session.commit()

    ResourcePlanningService(db_session).compute_schedule(plan_b.id)

    assert _rows(db_session, plan_b.id, "dev") == []
    [c] = _conflicts(db_session, plan_b.id, "UNPLACED_HOURS")
    assert c.backlog_item_id == item.id
    assert c.employee_id == ext.id


def test_busy_jira_executor_developer_is_replaced(db_session):
    """Исполнитель из Jira (не выбранный вручную) с ролью разработчика, у
    которого не хватает ёмкости квартала, уступает разработку свободному —
    как «Разработчик» из Jira. Выбранный вручную остаётся (см. выше)."""
    busy = make_employee(db_session, "Занятый", "B")
    free = make_employee(db_session, "Свободный", "B")
    from_jira = _item(db_session, dev=10, assignee=busy)
    manual = _item(db_session, dev=10, assignee=busy, manual=True)
    db_session.commit()

    # Ручная строка идёт первой и занимает 10 из 15 ч ёмкости «Занятого».
    res = ResourcePlanningService(db_session)._assign_employees(
        [manual, from_jira], [busy, free], capacity={busy.id: 15.0, free.id: 100.0}
    )

    assert res["dev"][from_jira.id] == free.id
    assert res["dev"][manual.id] == busy.id
