"""Подбор разработчика с учётом группы внутри команды (мягкий приоритет)."""
import uuid

from app.models import BacklogItem, Employee
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _emp(db_session, name: str, subgroup: str | None, team: str = "T1") -> Employee:
    e = Employee(
        jira_account_id=f"acc-{uuid.uuid4().hex[:12]}",
        display_name=name,
        role="developer",
        team=team,
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    db_session.add(
        EmployeeTeam(employee_id=e.id, team=team, is_primary=True, subgroup_id=subgroup)
    )
    db_session.commit()
    return e


def _item(db_session, dev_hours: float, priority: int) -> BacklogItem:
    item = BacklogItem(
        title=f"Init {priority}",
        estimate_analyst_hours=0.0,
        estimate_dev_hours=dev_hours,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        priority=priority,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_dev_from_own_subgroup(db_session):
    """Свой разработчик группы берётся, даже если сосед свободнее."""
    own = _emp(db_session, "Свой", "g1")
    neighbour = _emp(db_session, "Сосед", "g2")
    a = _item(db_session, 100.0, 9)
    b = _item(db_session, 100.0, 8)
    svc = ResourcePlanningService(db_session)
    res = svc._assign_employees(
        [a, b],
        [own, neighbour],
        emp_group={own.id: "g1", neighbour.id: "g2"},
        item_group={a.id: "g1", b.id: "g1"},
        capacity={own.id: 400.0, neighbour.id: 400.0},
    )
    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == own.id


def test_neighbour_taken_when_own_out_of_capacity(db_session):
    """Свой выбрал ёмкость квартала — работа уходит свободному соседу."""
    own = _emp(db_session, "Свой", "g1")
    neighbour = _emp(db_session, "Сосед", "g2")
    a = _item(db_session, 90.0, 9)
    b = _item(db_session, 90.0, 8)
    svc = ResourcePlanningService(db_session)
    res = svc._assign_employees(
        [a, b],
        [own, neighbour],
        emp_group={own.id: "g1", neighbour.id: "g2"},
        item_group={a.id: "g1", b.id: "g1"},
        capacity={own.id: 100.0, neighbour.id: 400.0},
    )
    # приоритетная задача осталась у своего, следующая ушла соседу
    assert res["dev"][a.id] == own.id
    assert res["dev"][b.id] == neighbour.id


def test_no_subgroups_keeps_old_behaviour(db_session):
    """Команда без деления — прежний greedy по минимальной нагрузке."""
    e1 = _emp(db_session, "Первый", None)
    e2 = _emp(db_session, "Второй", None)
    a = _item(db_session, 100.0, 9)
    b = _item(db_session, 100.0, 8)
    svc = ResourcePlanningService(db_session)
    res = svc._assign_employees([a, b], [e1, e2])
    assert {res["dev"][a.id], res["dev"][b.id]} == {e1.id, e2.id}
