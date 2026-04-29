"""Тест автосплита allocation по месяцам и ролям."""
from datetime import datetime
import pytest
from sqlalchemy.orm import Session
from app.models import (
    Employee, EmployeeTeam, PlanningScenario, ScenarioRevision,
    BacklogItem, ScenarioAllocation, ScenarioCapacitySnapshot,
    ScenarioAllocationBreakdownSnapshot,
)
from app.services.snapshot_writer import SnapshotWriter


@pytest.fixture
def fixed_caps_setup(db_session: Session):
    """Команда: 1 analyst (assignee), 1 RP, 2 devs. Available helpers зафиксированы вручную."""
    e_an = Employee(id="e-an", jira_account_id="j1", display_name="Аналитик А.", role="analyst", is_active=True)
    e_rp = Employee(id="e-rp", jira_account_id="j2", display_name="РП Р.", role="RP", is_active=True)
    e_d1 = Employee(id="e-d1", jira_account_id="j3", display_name="Девелопер 1", role="dev", is_active=True)
    e_d2 = Employee(id="e-d2", jira_account_id="j4", display_name="Девелопер 2", role="dev", is_active=True)
    db_session.add_all([e_an, e_rp, e_d1, e_d2])
    for i, emp in enumerate([e_an, e_rp, e_d1, e_d2]):
        db_session.add(EmployeeTeam(id=f"et-{i}", employee_id=emp.id, team="T1", is_primary=True))

    sc = PlanningScenario(id="s-1", name="Q2", year=2026, quarter="Q2", team="T1", status="draft")
    db_session.add(sc)
    rev = ScenarioRevision(id="r-1", scenario_id="s-1", revision_number=1, approved_at=datetime.utcnow())
    db_session.add(rev)

    # capacity snapshots вручную (имитируем результат write_capacity_snapshot)
    # Аналитик: 100/100/100 ч × 3 мес. РП: 80/80/80. Дев1: 60/60/60. Дев2: 40/40/40.
    for emp_id, hrs in [("e-an", 100), ("e-rp", 80), ("e-d1", 60), ("e-d2", 40)]:
        for m in [4, 5, 6]:
            db_session.add(ScenarioCapacitySnapshot(
                revision_id="r-1", employee_id=emp_id, employee_name="x",
                year=2026, month=m,
                norm_hours=hrs, available_hours=hrs, gross_hours=hrs,
                absence_hours=0.0, mandatory_hours=0.0, project_hours=hrs,
                snapshot_taken_at=datetime.utcnow(),
            ))
    db_session.commit()
    return {"scenario": sc, "revision": rev}


def test_breakdown_splits_analyst_to_assignee_proportional_to_months(db_session: Session, fixed_caps_setup):
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=30.0, estimate_dev_hours=0.0, estimate_qa_hours=0.0,
        estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
        assignee_employee_id="e-an",
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db_session.commit()

    rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="analyst"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    # 100/100/100 → равномерно 10/10/10
    assert len(rows) == 3
    assert all(r.employee_id == "e-an" for r in rows)
    assert all(r.is_external is False for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(30.0)
    assert rows[0].hours == pytest.approx(10.0)


def test_breakdown_splits_dev_into_pool_proportional_to_team_capacity(db_session: Session, fixed_caps_setup):
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=300.0,
        estimate_qa_hours=0.0, estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db_session.commit()

    rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="dev"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    # суммарный available dev = 100/мес × 3 = 300, всё равномерно по 100, делим 300 → 100/100/100
    assert len(rows) == 3
    assert all(r.employee_id is None for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(300.0)
    assert rows[0].hours == pytest.approx(100.0)


def test_breakdown_qa_external(db_session: Session, fixed_caps_setup):
    fixed_caps_setup["scenario"].external_qa_hours = 600.0
    db_session.commit()
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=0.0, estimate_qa_hours=60.0,
        estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db_session.commit()

    rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="qa"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    assert len(rows) == 3
    assert all(r.is_external is True for r in rows)
    assert all(r.employee_id is None for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(60.0)
    assert rows[0].hours == pytest.approx(20.0)


def test_breakdown_rp_to_single_team_rp(db_session: Session, fixed_caps_setup):
    bi = BacklogItem(
        id="bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=0.0, estimate_qa_hours=0.0,
        estimate_opo_hours=30.0, opo_analyst_ratio=0.5,
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="al-1", scenario_id="s-1", backlog_item_id="bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    writer.write_allocation_breakdown(revision=fixed_caps_setup["revision"], scenario=fixed_caps_setup["scenario"])
    db_session.commit()

    rp_rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="r-1", role="RP"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()
    # ОПЭ=30, аналитик-доля=0.5 → 15 ч аналитику + 15 ч РП. Аналитик assignee нет (NULL) — равномерно. РП → e-rp.
    assert len(rp_rows) == 3
    assert all(r.employee_id == "e-rp" for r in rp_rows)
    assert sum(r.hours for r in rp_rows) == pytest.approx(15.0)
