"""Тесты ролевой логики назначения в ResourcePlanningService."""
import uuid

from app.models import (
    BacklogItem,
    Employee,
)
from app.models.employee_team import EmployeeTeam
from app.services.resource_planning_service import ResourcePlanningService


def _make_emp(db_session, name: str, role: str, team: str = "T1") -> Employee:
    e = Employee(
        jira_account_id=f"acc-{uuid.uuid4().hex[:12]}",
        display_name=name,
        role=role,
        team=team,
        is_active=True,
    )
    db_session.add(e)
    db_session.commit()
    db_session.refresh(e)
    et = EmployeeTeam(employee_id=e.id, team=team, is_primary=True)
    db_session.add(et)
    db_session.commit()
    return e


def _make_item(db_session, **kwargs) -> BacklogItem:
    defaults = dict(
        title="Init",
        estimate_analyst_hours=0.0,
        estimate_dev_hours=0.0,
        estimate_qa_hours=0.0,
        estimate_opo_hours=0.0,
        opo_analyst_ratio=0.5,
    )
    defaults.update(kwargs)
    item = BacklogItem(**defaults)
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


# ── analyst phase ──────────────────────────────────────────────────────────


def test_analyst_assigned_from_assignee(db_session):
    """Аналитик берётся из исполнителя инициативы (роль analyst)."""
    analyst = _make_emp(db_session, "Иванов", "analyst")
    other = _make_emp(db_session, "Сидоров", "analyst")
    item = _make_item(
        db_session,
        estimate_analyst_hours=40.0,
        assignee_employee_id=analyst.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [analyst, other])
    assert result["analyst"][item.id] == analyst.id


def test_analyst_role_pm_or_consultant_accepted(db_session):
    """РП и Консультант тоже годятся как analyst."""
    pm = _make_emp(db_session, "Петров", "rp")
    item = _make_item(
        db_session,
        estimate_analyst_hours=10.0,
        assignee_employee_id=pm.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [pm])
    assert result["analyst"][item.id] == pm.id


def test_analyst_role_consultant_accepted(db_session):
    """Консультант тоже годится как analyst."""
    consultant = _make_emp(db_session, "К", "консультант")
    item = _make_item(
        db_session,
        estimate_analyst_hours=10.0,
        assignee_employee_id=consultant.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [consultant])
    assert result["analyst"][item.id] == consultant.id


def test_analyst_none_if_assignee_role_not_acceptable(db_session):
    """Если роль исполнителя — dev, аналитик не назначается."""
    dev = _make_emp(db_session, "Разраб", "developer")
    item = _make_item(
        db_session,
        estimate_analyst_hours=10.0,
        assignee_employee_id=dev.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [dev])
    assert result["analyst"].get(item.id) is None


def test_analyst_none_if_no_assignee(db_session):
    """Без исполнителя аналитик не определяется."""
    analyst = _make_emp(db_session, "Иванов", "analyst")
    item = _make_item(
        db_session,
        estimate_analyst_hours=10.0,
        assignee_employee_id=None,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [analyst])
    assert result["analyst"].get(item.id) is None


# ── dev phase ──────────────────────────────────────────────────────────────


def test_dev_assigned_from_dev_pool(db_session):
    """Программист назначается greedy из пула с role=developer."""
    analyst = _make_emp(db_session, "А", "analyst")
    dev1 = _make_emp(db_session, "Д1", "developer")
    dev2 = _make_emp(db_session, "Д2", "developer")
    item = _make_item(
        db_session,
        estimate_dev_hours=20.0,
        assignee_employee_id=analyst.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [analyst, dev1, dev2])
    assert result["dev"][item.id] in (dev1.id, dev2.id)


def test_dev_fallback_to_all_if_no_dev_pool(db_session):
    """Если нет dev-сотрудников — fallback на всех."""
    analyst = _make_emp(db_session, "А", "analyst")
    item = _make_item(
        db_session,
        estimate_dev_hours=10.0,
        assignee_employee_id=analyst.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [analyst])
    assert result["dev"][item.id] == analyst.id


# ── qa phase ───────────────────────────────────────────────────────────────


def test_qa_employee_id_is_none(db_session):
    """QA — без сотрудника."""
    dev = _make_emp(db_session, "Разраб", "developer")
    item = _make_item(
        db_session,
        estimate_qa_hours=20.0,
        estimate_dev_hours=10.0,
        assignee_employee_id=dev.id,
    )
    svc = ResourcePlanningService(db_session)
    result = svc._assign_employees([item], [dev])
    assert result["qa"].get(item.id) is None


# ── opo split ──────────────────────────────────────────────────────────────


def test_opo_split_returns_two_parts(db_session):
    """_opo_split разбивает часы 30/70 при ratio=0.3."""
    analyst = _make_emp(db_session, "Иванов", "analyst")
    dev = _make_emp(db_session, "Петров", "developer")
    item = _make_item(
        db_session,
        estimate_opo_hours=20.0,
        opo_analyst_ratio=0.3,
        assignee_employee_id=analyst.id,
    )
    svc = ResourcePlanningService(db_session)
    parts = svc._opo_split(item, analyst.id, dev.id)
    assert len(parts) == 2
    assert parts[0] == (analyst.id, 6.0)
    assert parts[1] == (dev.id, 14.0)


def test_opo_default_ratio_50_50(db_session):
    """Если ratio NULL — 50/50."""
    analyst = _make_emp(db_session, "А", "analyst")
    dev = _make_emp(db_session, "Б", "developer")
    item = _make_item(
        db_session,
        estimate_opo_hours=10.0,
        opo_analyst_ratio=None,
        assignee_employee_id=analyst.id,
    )
    svc = ResourcePlanningService(db_session)
    parts = svc._opo_split(item, analyst.id, dev.id)
    assert parts == [(analyst.id, 5.0), (dev.id, 5.0)]


# ── pinned override ────────────────────────────────────────────────────────


def test_pinned_employee_overrides_logic(db_session):
    """Если есть pin для (item, dev, 1), assign возвращает pinned employee."""
    analyst = _make_emp(db_session, "А1", "analyst")
    pinned_dev = _make_emp(db_session, "Закреплённый", "developer")
    other_dev = _make_emp(db_session, "Свободный", "developer")
    item = _make_item(
        db_session,
        estimate_dev_hours=20.0,
        assignee_employee_id=analyst.id,
    )
    svc = ResourcePlanningService(db_session)
    pinned = {(item.id, "dev", 1): pinned_dev.id}
    result = svc._assign_employees(
        [item], [analyst, pinned_dev, other_dev], pinned=pinned
    )
    assert result["dev"][item.id] == pinned_dev.id


def test_pinned_analyst_overrides_assignee(db_session):
    """Pin для analyst-фазы перебивает выбор по assignee."""
    assignee = _make_emp(db_session, "Назн", "analyst")
    pinned_an = _make_emp(db_session, "Зафикс", "analyst")
    item = _make_item(
        db_session,
        estimate_analyst_hours=10.0,
        assignee_employee_id=assignee.id,
    )
    svc = ResourcePlanningService(db_session)
    pinned = {(item.id, "analyst", 1): pinned_an.id}
    result = svc._assign_employees(
        [item], [assignee, pinned_an], pinned=pinned
    )
    assert result["analyst"][item.id] == pinned_an.id
