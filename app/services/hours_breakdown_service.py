"""HoursBreakdownService — расчёт 6 колонок часов длинной RFA.

См. spec: docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md
"""
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from app.models import (
    Issue, Worklog, Employee, BacklogItem, ScenarioAllocation, PlanningScenario,
)

ROLES = ("analyst", "dev", "qa", "opo")
QUARTER_MONTHS = {1: (1, 2, 3), 2: (4, 5, 6), 3: (7, 8, 9), 4: (10, 11, 12)}
_QUARTER_END_DAY = {3: 31, 6: 30, 9: 30, 12: 31}


def quarter_range(year: int, quarter: int) -> tuple[date, date]:
    """Возвращает первый и последний день квартала."""
    months = QUARTER_MONTHS[quarter]
    start = date(year, months[0], 1)
    end = date(year, months[-1], _QUARTER_END_DAY[months[-1]])
    return start, end


class HoursBreakdownService:
    def __init__(self, db: Session):
        self.db = db

    def _subtree_ids(self, root_id: str) -> Set[str]:
        """Все ID в поддереве: root + все потомки на любую глубину."""
        result: Set[str] = {root_id}
        frontier: List[str] = [root_id]
        while frontier:
            children = (
                self.db.query(Issue.id)
                .filter(Issue.parent_id.in_(frontier))
                .all()
            )
            new_ids = [c[0] for c in children if c[0] not in result]
            if not new_ids:
                break
            result.update(new_ids)
            frontier = new_ids
        return result

    def _approved_subtree_ids(self, subtree: Set[str], year: int, quarter: int) -> Set[str]:
        """ID задач поддерева, которые утверждены в сценарии (year, quarter)."""
        quarter_str = f"Q{quarter}"
        rows = (
            self.db.query(Issue.id)
            .join(BacklogItem, BacklogItem.issue_id == Issue.id)
            .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .filter(
                Issue.id.in_(subtree),
                PlanningScenario.year == year,
                PlanningScenario.quarter == quarter_str,
                PlanningScenario.status == "approved",
                ScenarioAllocation.included_flag == True,  # noqa: E712
            )
            .distinct()
            .all()
        )
        return {r[0] for r in rows}

    def _aggregate_worklog(
        self, issue_ids: Set[str], start: date, end: date
    ) -> Dict[str, float]:
        """Σ worklog.hours разбитые по роли Employee за период [start, end]."""
        out: Dict[str, float] = {r: 0.0 for r in ROLES}
        if not issue_ids:
            return out
        start_dt = datetime.combine(start, time.min)
        end_dt = datetime.combine(end, time.max)
        rows = (
            self.db.query(Employee.role, Worklog.hours)
            .join(Worklog, Worklog.employee_id == Employee.id)
            .filter(
                Worklog.issue_id.in_(issue_ids),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
            .all()
        )
        for emp_role, hours in rows:
            role = (emp_role or "").lower()
            if role in ROLES:
                out[role] += float(hours or 0)
        return out

    def _aggregate_plan(self, issue_ids: Set[str]) -> Dict[str, float]:
        """Σ effective плановых часов (manual ?? jira) по issue_ids per роль."""
        out: Dict[str, float] = {r: 0.0 for r in ROLES}
        if not issue_ids:
            return out
        issues = self.db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
        for issue in issues:
            for role in ROLES:
                jira = getattr(issue, f"planned_{role}_hours_jira") or 0
                manual = getattr(issue, f"planned_{role}_hours_manual")
                eff = manual if manual is not None else jira
                out[role] += float(eff or 0)
        return out

    def _issue_has_worklog(self, issue_id: str) -> bool:
        return (
            self.db.query(Worklog.id)
            .filter(Worklog.issue_id == issue_id)
            .first() is not None
        )

    def calculate(self, root_issue_id: str, year: int, quarter: int) -> dict:
        """Рассчитать 6 колонок часов для RFA.

        Args:
            root_issue_id: ID корневой задачи (RFA/ITL).
            year: Год квартала.
            quarter: Номер квартала (1..4).

        Returns:
            Словарь с ключами plan/fact_past/fact_current/approved/planable/draft,
            каждый — dict {analyst, dev, qa, opo, total}, плюс flags.
        """
        subtree = self._subtree_ids(root_issue_id)
        descendants = subtree - {root_issue_id}
        q_start, q_end = quarter_range(year, quarter)

        plan = self._aggregate_plan({root_issue_id})
        fact_past = self._aggregate_worklog(
            subtree, date(2000, 1, 1), q_start - timedelta(days=1)
        )

        approved_ids = self._approved_subtree_ids(subtree, year, quarter)
        fact_current = self._aggregate_worklog(approved_ids, q_start, q_end)
        approved = self._aggregate_plan(approved_ids)

        draft_ids: Set[str] = set()
        for iid in descendants:
            if iid in approved_ids:
                continue
            if self._issue_has_worklog(iid):
                continue
            draft_ids.add(iid)
        draft = self._aggregate_plan(draft_ids)

        planable = {r: plan[r] - fact_past[r] - approved[r] for r in ROLES}

        flags = {
            "overrun": any(planable[r] < 0 for r in ROLES),
            "plan_missing": all(plan[r] == 0 for r in ROLES),
            "draft_exceeds_planable": any(draft[r] > planable[r] for r in ROLES),
        }

        def _with_total(d: Dict[str, float]) -> dict:
            out = {r: d[r] for r in ROLES}
            out["total"] = sum(out.values())
            return out

        return {
            "issue_id": root_issue_id,
            "year": year,
            "quarter": quarter,
            "plan": _with_total(plan),
            "fact_past": _with_total(fact_past),
            "fact_current": _with_total(fact_current),
            "approved": _with_total(approved),
            "planable": _with_total(planable),
            "draft": _with_total(draft),
            "flags": flags,
        }
