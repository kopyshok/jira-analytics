"""Тесты plan diff — сравнение baseline vs scenario."""

from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import ResourcePlan, ResourcePlanAssignment
from app.services.plan_diff import diff_plans

# Force model registry import
import app.models  # noqa: F401


def _make_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_diff_detects_assignment_date_shift():
    db = _make_session()
    base = ResourcePlan(
        team="T", quarter="Q2", year=2026, status="ready", is_baseline=True
    )
    scen = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db.add_all([base, scen])
    db.commit()
    db.refresh(base)
    db.refresh(scen)

    db.add(
        ResourcePlanAssignment(
            plan_id=base.id,
            backlog_item_id="BI-1",
            phase="dev",
            employee_id="EMP-1",
            part_number=1,
            hours_allocated=10.0,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
        )
    )
    db.add(
        ResourcePlanAssignment(
            plan_id=scen.id,
            backlog_item_id="BI-1",
            phase="dev",
            employee_id="EMP-1",
            part_number=1,
            hours_allocated=10.0,
            start_date=date(2026, 4, 8),
            end_date=date(2026, 4, 12),
        )
    )
    db.commit()

    result = diff_plans(db, base.id, scen.id)
    shifts = result["assignment_shifts"]
    assert len(shifts) == 1
    assert shifts[0]["backlog_item_id"] == "BI-1"
    assert shifts[0]["start_delta_days"] == 7
    assert shifts[0]["kind"] == "shifted"


def test_diff_detects_added_and_removed_assignments():
    db = _make_session()
    base = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    scen = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db.add_all([base, scen])
    db.commit()
    db.refresh(base)
    db.refresh(scen)

    db.add(
        ResourcePlanAssignment(
            plan_id=base.id,
            backlog_item_id="BI-OLD",
            phase="dev",
            employee_id="EMP-1",
            part_number=1,
            hours_allocated=10.0,
        )
    )
    db.add(
        ResourcePlanAssignment(
            plan_id=scen.id,
            backlog_item_id="BI-NEW",
            phase="dev",
            employee_id="EMP-1",
            part_number=1,
            hours_allocated=10.0,
        )
    )
    db.commit()

    result = diff_plans(db, base.id, scen.id)
    kinds = {s["kind"] for s in result["assignment_shifts"]}
    assert "added" in kinds
    assert "removed" in kinds


def test_diff_metrics_count_assignments_and_critical_path():
    db = _make_session()
    base = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    scen = ResourcePlan(team="T", quarter="Q2", year=2026, status="ready")
    db.add_all([base, scen])
    db.commit()
    db.refresh(base)
    db.refresh(scen)

    db.add(
        ResourcePlanAssignment(
            plan_id=base.id,
            backlog_item_id="BI-1",
            phase="dev",
            part_number=1,
            is_on_critical_path=True,
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 5),
        )
    )
    db.commit()

    result = diff_plans(db, base.id, scen.id)
    assert result["baseline_metrics"]["assignments_count"] == 1
    assert result["baseline_metrics"]["critical_path_count"] == 1
    assert result["scenario_metrics"]["assignments_count"] == 0


def test_diff_unknown_plan_raises():
    import pytest

    db = _make_session()
    with pytest.raises(ValueError):
        diff_plans(db, "no-such-base", "no-such-scen")
