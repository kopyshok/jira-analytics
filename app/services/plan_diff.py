"""Plan diff — сравнение метрик и assignment-сдвигов между двумя планами."""

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ResourcePlan, ResourcePlanAssignment, PlanConflict
from app.models.backlog_item import BacklogItem


def diff_plans(db: Session, baseline_id: str, scenario_id: str) -> Dict:
    """Возвращает структурированный diff baseline → scenario."""
    base = db.get(ResourcePlan, baseline_id)
    scen = db.get(ResourcePlan, scenario_id)
    if not base or not scen:
        raise ValueError("Plan not found")

    base_a = (
        db.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == baseline_id
            )
        )
        .scalars()
        .all()
    )
    scen_a = (
        db.execute(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == scenario_id
            )
        )
        .scalars()
        .all()
    )

    all_item_ids = {a.backlog_item_id for a in base_a + scen_a if a.backlog_item_id}
    titles: Dict[str, str] = {}
    if all_item_ids:
        title_rows = (
            db.execute(select(BacklogItem).where(BacklogItem.id.in_(all_item_ids)))
            .scalars()
            .all()
        )
        titles = {b.id: b.title for b in title_rows}

    base_by_key = {(a.backlog_item_id, a.phase, a.part_number): a for a in base_a}
    scen_by_key = {(a.backlog_item_id, a.phase, a.part_number): a for a in scen_a}

    shifts: List[Dict] = []
    for key, scen_v in scen_by_key.items():
        base_v = base_by_key.get(key)
        if not base_v:
            shifts.append(
                {
                    "backlog_item_id": key[0],
                    "backlog_item_title": titles.get(key[0]),
                    "phase": key[1],
                    "part_number": key[2],
                    "kind": "added",
                }
            )
            continue
        if (
            base_v.start_date
            and scen_v.start_date
            and base_v.start_date != scen_v.start_date
        ):
            shifts.append(
                {
                    "backlog_item_id": key[0],
                    "backlog_item_title": titles.get(key[0]),
                    "phase": key[1],
                    "part_number": key[2],
                    "kind": "shifted",
                    "start_delta_days": (scen_v.start_date - base_v.start_date).days,
                    "end_delta_days": (scen_v.end_date - base_v.end_date).days
                    if base_v.end_date and scen_v.end_date
                    else 0,
                    "employee_changed": base_v.employee_id != scen_v.employee_id,
                }
            )
    for key in base_by_key:
        if key not in scen_by_key:
            shifts.append(
                {
                    "backlog_item_id": key[0],
                    "backlog_item_title": titles.get(key[0]),
                    "phase": key[1],
                    "part_number": key[2],
                    "kind": "removed",
                }
            )

    base_conflicts = (
        db.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == baseline_id,
                PlanConflict.status == "open",
            )
        )
        .scalars()
        .all()
    )
    scen_conflicts = (
        db.execute(
            select(PlanConflict).where(
                PlanConflict.plan_id == scenario_id,
                PlanConflict.status == "open",
            )
        )
        .scalars()
        .all()
    )

    def _metrics(assigns, conflicts):
        crit = sum(1 for a in assigns if a.is_on_critical_path)
        end = max((a.end_date for a in assigns if a.end_date), default=None)
        return {
            "assignments_count": len(assigns),
            "critical_path_count": crit,
            "last_end_date": end.isoformat() if end else None,
            "conflicts_open": len(conflicts),
            "conflicts_critical": sum(1 for c in conflicts if c.severity == "critical"),
        }

    return {
        "baseline_id": baseline_id,
        "scenario_id": scenario_id,
        "assignment_shifts": shifts,
        "baseline_metrics": _metrics(base_a, base_conflicts),
        "scenario_metrics": _metrics(scen_a, scen_conflicts),
    }
