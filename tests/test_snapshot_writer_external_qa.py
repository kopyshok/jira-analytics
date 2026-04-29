"""Edge cases для SnapshotWriter.write_allocation_breakdown."""
from datetime import datetime
import pytest
from sqlalchemy.orm import Session
from app.models import (
    Employee, EmployeeTeam, PlanningScenario, ScenarioRevision,
    BacklogItem, ScenarioAllocation, ScenarioCapacitySnapshot,
    ScenarioAllocationBreakdownSnapshot,
)
from app.services.snapshot_writer import SnapshotWriter


def _add_capacity_rows(db: Session, revision_id: str, employee_id: str, hours: float) -> None:
    """Добавляет 3 строки capacity snapshot (апр/май/июн 2026) для сотрудника."""
    for m in [4, 5, 6]:
        db.add(ScenarioCapacitySnapshot(
            revision_id=revision_id,
            employee_id=employee_id,
            employee_name="x",
            year=2026,
            month=m,
            norm_hours=hours,
            available_hours=hours,
            gross_hours=hours,
            absence_hours=0.0,
            mandatory_hours=0.0,
            project_hours=hours,
            snapshot_taken_at=datetime.utcnow(),
        ))


def test_breakdown_rp_null_when_no_rp_in_team(db_session: Session):
    """0 РП в команде → строки с role='RP' имеют employee_id=None (сигнал «не назначено»)."""
    e_an = Employee(id="eq-e-an", jira_account_id="eq-j1", display_name="Аналитик", role="analyst", is_active=True)
    db_session.add(e_an)
    db_session.add(EmployeeTeam(id="eq-et-0", employee_id="eq-e-an", team="EQ1", is_primary=True))

    sc = PlanningScenario(id="eq-s-1", name="Q2", year=2026, quarter="Q2", team="EQ1", status="draft")
    db_session.add(sc)
    rev = ScenarioRevision(id="eq-r-1", scenario_id="eq-s-1", revision_number=1, approved_at=datetime.utcnow())
    db_session.add(rev)

    _add_capacity_rows(db_session, "eq-r-1", "eq-e-an", 100.0)
    db_session.commit()

    # estimate_opo_hours=30, opo_analyst_ratio=0.5 → rp_total=15
    bi = BacklogItem(
        id="eq-bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=0.0, estimate_qa_hours=0.0,
        estimate_opo_hours=30.0, opo_analyst_ratio=0.5,
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="eq-al-1", scenario_id="eq-s-1", backlog_item_id="eq-bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=rev, scenario=sc)
    writer.write_allocation_breakdown(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="eq-r-1", role="RP"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()

    assert len(rows) == 3
    assert all(r.employee_id is None for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(15.0)


def test_breakdown_rp_picks_alphabetical_first(db_session: Session):
    """Два РП в команде → все строки role='RP' указывают на первого по алфавиту."""
    e_rp_z = Employee(id="eq2-e-rp-z", jira_account_id="eq2-j1", display_name="Я-Зоркий", role="RP", is_active=True)
    e_rp_a = Employee(id="eq2-e-rp-a", jira_account_id="eq2-j2", display_name="А-Активный", role="RP", is_active=True)
    db_session.add_all([e_rp_z, e_rp_a])
    db_session.add(EmployeeTeam(id="eq2-et-0", employee_id="eq2-e-rp-z", team="EQ2", is_primary=True))
    db_session.add(EmployeeTeam(id="eq2-et-1", employee_id="eq2-e-rp-a", team="EQ2", is_primary=True))

    sc = PlanningScenario(id="eq2-s-1", name="Q2", year=2026, quarter="Q2", team="EQ2", status="draft")
    db_session.add(sc)
    rev = ScenarioRevision(id="eq2-r-1", scenario_id="eq2-s-1", revision_number=1, approved_at=datetime.utcnow())
    db_session.add(rev)

    _add_capacity_rows(db_session, "eq2-r-1", "eq2-e-rp-z", 80.0)
    _add_capacity_rows(db_session, "eq2-r-1", "eq2-e-rp-a", 80.0)
    db_session.commit()

    bi = BacklogItem(
        id="eq2-bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=0.0, estimate_qa_hours=0.0,
        estimate_opo_hours=30.0, opo_analyst_ratio=0.5,
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="eq2-al-1", scenario_id="eq2-s-1", backlog_item_id="eq2-bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=rev, scenario=sc)
    writer.write_allocation_breakdown(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="eq2-r-1", role="RP"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()

    assert len(rows) == 3
    # «А-Активный» идёт первым по алфавиту
    assert all(r.employee_id == "eq2-e-rp-a" for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(15.0)


def test_breakdown_dev_null_when_no_dev_in_team(db_session: Session):
    """Нет devов в команде + estimate_dev_hours>0 → 3 строки role='dev', employee_id=None, is_external=False, sum==30."""
    e_an = Employee(id="eq3-e-an", jira_account_id="eq3-j1", display_name="Аналитик", role="analyst", is_active=True)
    db_session.add(e_an)
    db_session.add(EmployeeTeam(id="eq3-et-0", employee_id="eq3-e-an", team="EQ3", is_primary=True))

    sc = PlanningScenario(id="eq3-s-1", name="Q2", year=2026, quarter="Q2", team="EQ3", status="draft")
    db_session.add(sc)
    rev = ScenarioRevision(id="eq3-r-1", scenario_id="eq3-s-1", revision_number=1, approved_at=datetime.utcnow())
    db_session.add(rev)

    _add_capacity_rows(db_session, "eq3-r-1", "eq3-e-an", 100.0)
    db_session.commit()

    bi = BacklogItem(
        id="eq3-bi-1", title="Инициатива",
        estimate_analyst_hours=0.0, estimate_dev_hours=30.0, estimate_qa_hours=0.0,
        estimate_opo_hours=0.0, opo_analyst_ratio=0.5,
    )
    db_session.add(bi)
    db_session.add(ScenarioAllocation(id="eq3-al-1", scenario_id="eq3-s-1", backlog_item_id="eq3-bi-1", included_flag=True))
    db_session.commit()

    writer = SnapshotWriter(db_session)
    writer.write_allocation_snapshot(revision=rev, scenario=sc)
    writer.write_allocation_breakdown(revision=rev, scenario=sc)
    db_session.commit()

    rows = db_session.query(ScenarioAllocationBreakdownSnapshot).filter_by(
        revision_id="eq3-r-1", role="dev"
    ).order_by(ScenarioAllocationBreakdownSnapshot.month).all()

    assert len(rows) == 3
    assert all(r.employee_id is None for r in rows)
    assert all(r.is_external is False for r in rows)
    assert sum(r.hours for r in rows) == pytest.approx(30.0)
    # равномерный split: 10/10/10
    assert rows[0].hours == pytest.approx(10.0)
