"""Привлечение сотрудников из чужих команд в ресурсный план."""

from datetime import date

from app.models import BacklogItem
from app.services.resource_planning_service import ResourcePlanningService
from tests.services.xteam_factory import make_employee

D = date.fromisoformat


def test_borrowed_employee_is_available_outside_plan_team(db_session):
    e = make_employee(db_session, "Чужой", "A")
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    plain = svc.build_availability([e], D("2026-01-05"), D("2026-01-05"), [], team="B")
    borrowed = svc.build_availability(
        [e], D("2026-01-05"), D("2026-01-05"), [], team="B", borrowed={e.id}
    )

    assert plain[e.id][D("2026-01-05")] == 0.0
    assert borrowed[e.id][D("2026-01-05")] == 6.0


def _plain_item(db, title="x", dev=10.0, analyst=0.0, assignee=None, priority=1):
    it = BacklogItem(
        title=title, priority=priority, estimate_dev_hours=dev,
        estimate_analyst_hours=analyst, estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        assignee_employee_id=assignee.id if assignee else None,
    )
    db.add(it)
    db.flush()
    return it


def test_jira_developer_from_other_team_wins(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _plain_item(db_session)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], jira_dev={item.id: ext.id}, borrowed={ext.id}
    )

    assert res["dev"][item.id] == ext.id


def test_manual_pin_beats_jira_developer(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    item = _plain_item(db_session)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [item], [own, ext], pinned={(item.id, "dev", 1): own.id},
        jira_dev={item.id: ext.id}, borrowed={ext.id},
    )

    assert res["dev"][item.id] == own.id


def test_greedy_pool_skips_borrowed(db_session):
    own = make_employee(db_session, "Свой", "B")
    ext = make_employee(db_session, "Чужой", "A")
    a = _plain_item(db_session, "a", priority=2)
    b = _plain_item(db_session, "b", priority=1)
    db_session.commit()

    res = ResourcePlanningService(db_session)._assign_employees(
        [a, b], [own, ext], borrowed={ext.id}
    )

    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == own.id


def test_analyst_from_other_team_only_manual(db_session):
    b_an = make_employee(db_session, "Аналитик B", "B", role="analyst")
    ext_an = make_employee(db_session, "Аналитик A", "A", role="analyst")
    item = _plain_item(db_session, dev=0.0, analyst=10.0, assignee=ext_an)
    db_session.commit()
    svc = ResourcePlanningService(db_session)

    auto = svc._assign_employees([item], [b_an, ext_an], borrowed={ext_an.id})
    manual = svc._assign_employees(
        [item], [b_an, ext_an], pinned={(item.id, "analyst", 1): ext_an.id},
        borrowed={ext_an.id},
    )

    assert auto["analyst"][item.id] == b_an.id
    assert manual["analyst"][item.id] == ext_an.id
