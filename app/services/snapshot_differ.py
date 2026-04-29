"""SnapshotDiffer — diff между двумя ревизиями по snapshot-таблицам."""
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    ScenarioAllocationSnapshot,
    ScenarioCapacitySnapshot,
    ScenarioNormSnapshot,
    ScenarioRulesSnapshot,
    ScenarioTeamSnapshot,
)


_ALLOC_COMPARE_FIELDS = (
    "estimate_analyst_hours",
    "estimate_dev_hours",
    "estimate_qa_hours",
    "estimate_opo_hours",
    "opo_analyst_ratio",
    "involvement_coefficient",
    "impact",
    "risk",
    "customer",
    "cost_type",
    "title",
    "assignee_employee_id",
    "assignee_role_at_approval",
    "priority",
)


class SnapshotDiffer:
    """Сравнивает две ревизии сценария по всем snapshot-таблицам."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def diff(self, *, revision_id: str, against_revision_id: str) -> dict[str, Any]:
        """Вернуть полный diff между revision_id (после) и against_revision_id (до)."""
        return {
            "allocations": self._diff_allocations(revision_id, against_revision_id),
            "team": self._diff_team(revision_id, against_revision_id),
            "rules": self._diff_rules(revision_id, against_revision_id),
            "external_qa_total_hours": self._diff_external_qa(revision_id, against_revision_id),
            "capacity_changes": self._diff_capacity(revision_id, against_revision_id),
        }

    # ------------------------------------------------------------------ #
    # private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _diff_allocations(self, rid: str, against: str) -> dict[str, list[dict]]:
        cur = {
            a.allocation_id: a
            for a in self.db.query(ScenarioAllocationSnapshot).filter_by(revision_id=rid).all()
            if a.allocation_id
        }
        prev = {
            a.allocation_id: a
            for a in self.db.query(ScenarioAllocationSnapshot).filter_by(revision_id=against).all()
            if a.allocation_id
        }

        added = [self._alloc_to_dict(cur[k]) for k in cur if k not in prev]
        removed = [self._alloc_to_dict(prev[k]) for k in prev if k not in cur]
        changed: list[dict] = []
        for k in cur:
            if k not in prev:
                continue
            diff_fields: dict[str, dict] = {}
            for field in _ALLOC_COMPARE_FIELDS:
                after_val = getattr(cur[k], field)
                before_val = getattr(prev[k], field)
                if after_val != before_val:
                    diff_fields[field] = {"before": before_val, "after": after_val}
            if diff_fields:
                changed.append({"allocation_id": k, **diff_fields})
        return {"added": added, "removed": removed, "changed": changed}

    @staticmethod
    def _alloc_to_dict(a: ScenarioAllocationSnapshot) -> dict:
        return {
            "allocation_id": a.allocation_id,
            "backlog_item_id": a.backlog_item_id,
            "title": a.title,
            "estimate_analyst_hours": a.estimate_analyst_hours,
            "estimate_dev_hours": a.estimate_dev_hours,
            "estimate_qa_hours": a.estimate_qa_hours,
            "estimate_opo_hours": a.estimate_opo_hours,
        }

    def _diff_team(self, rid: str, against: str) -> dict[str, list[dict]]:
        cur = {
            t.employee_id: t
            for t in self.db.query(ScenarioTeamSnapshot).filter_by(revision_id=rid).all()
            if t.employee_id
        }
        prev = {
            t.employee_id: t
            for t in self.db.query(ScenarioTeamSnapshot).filter_by(revision_id=against).all()
            if t.employee_id
        }

        added = [
            {"employee_id": k, "display_name": cur[k].display_name, "role": cur[k].role}
            for k in cur if k not in prev
        ]
        removed = [
            {"employee_id": k, "display_name": prev[k].display_name, "role": prev[k].role}
            for k in prev if k not in cur
        ]
        role_changed = [
            {
                "employee_id": k,
                "display_name": cur[k].display_name,
                "role": {"before": prev[k].role, "after": cur[k].role},
            }
            for k in cur
            if k in prev and cur[k].role != prev[k].role
        ]
        return {"added": added, "removed": removed, "role_changed": role_changed}

    def _diff_rules(self, rid: str, against: str) -> dict[str, list[dict]]:
        def _key(r: ScenarioRulesSnapshot) -> tuple:
            return (r.role, r.work_type_id)

        cur = {_key(r): r for r in self.db.query(ScenarioRulesSnapshot).filter_by(revision_id=rid).all()}
        prev = {_key(r): r for r in self.db.query(ScenarioRulesSnapshot).filter_by(revision_id=against).all()}

        added = [
            {
                "role": k[0],
                "work_type_id": k[1],
                "work_type_label": cur[k].work_type_label,
                "pct_of_norm": cur[k].pct_of_norm,
            }
            for k in cur if k not in prev
        ]
        removed = [
            {
                "role": k[0],
                "work_type_id": k[1],
                "work_type_label": prev[k].work_type_label,
                "pct_of_norm": prev[k].pct_of_norm,
            }
            for k in prev if k not in cur
        ]
        changed = [
            {
                "role": k[0],
                "work_type_id": k[1],
                "work_type_label": cur[k].work_type_label,
                "pct_of_norm": {"before": prev[k].pct_of_norm, "after": cur[k].pct_of_norm},
            }
            for k in cur
            if k in prev and cur[k].pct_of_norm != prev[k].pct_of_norm
        ]
        return {"added": added, "removed": removed, "changed": changed}

    def _diff_external_qa(self, rid: str, against: str) -> dict[str, float]:
        def _total(rev_id: str) -> float:
            rows = (
                self.db.query(ScenarioNormSnapshot)
                .filter_by(revision_id=rev_id, is_external=True)
                .all()
            )
            return round(sum(r.norm_hours for r in rows), 2)

        return {"before": _total(against), "after": _total(rid)}

    def _diff_capacity(self, rid: str, against: str) -> list[dict]:
        cur = {
            (r.employee_id, r.month): r
            for r in self.db.query(ScenarioCapacitySnapshot).filter_by(revision_id=rid).all()
            if r.employee_id
        }
        prev = {
            (r.employee_id, r.month): r
            for r in self.db.query(ScenarioCapacitySnapshot).filter_by(revision_id=against).all()
            if r.employee_id
        }
        out: list[dict] = []
        for k in cur:
            if k not in prev:
                continue
            if cur[k].available_hours != prev[k].available_hours:
                out.append({
                    "employee_id": k[0],
                    "month": k[1],
                    "available_hours": {
                        "before": float(prev[k].available_hours),
                        "after": float(cur[k].available_hours),
                    },
                })
        return out
