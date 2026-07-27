"""Проектный срез плана: план/факт по видам работ, задачи, таймлайн.

Отличие от рабочих столов: там персональная доля одного сотрудника, здесь —
проект целиком, со всеми исполнителями. Формулы общие, живут в plan_common.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.services.plan_common import (
    DISPLAY_ROLES,
    PHASE_LABEL,
    jira_url,
    plan_ids_for_issues,
    quarter_bounds,
    role_breakdown,
    subtree_ids,
    team_member_ids,
)


class ProjectPlanService:
    """Агрегаты вкладки «План и сроки» и сводного экрана портфеля."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Один проект
    # ------------------------------------------------------------------

    def get_plan(self, key: str, *, year: int, quarter: int) -> Optional[dict]:
        """Контракт вкладки «План и сроки». None — задача с таким ключом не найдена."""
        from app.models import Issue

        root = self._db.execute(select(Issue).where(Issue.key == key)).scalars().first()
        if root is None:
            return None

        q_start, q_end = quarter_bounds(year, quarter)
        subtree = subtree_ids(self._db, [root.id])
        plan_ids = plan_ids_for_issues(self._db, [root.id])
        team_ids = team_member_ids(self._db, self._project_teams(root, plan_ids))
        bd = role_breakdown(
            self._db, plan_ids, [root.id], subtree, q_end, team_ids
        )[root.id]

        work_types, total_plan, total_fact = _project_work_types(bd)
        return {
            "key": root.key,
            "work_types": work_types,
            "external_hours": round(bd["info"], 1),
            "total_plan": total_plan,
            "total_fact": total_fact,
            "total_pct": _pct(total_fact, total_plan),
            "timeline": self._timeline(plan_ids, [root.id], q_start, q_end),
            "children": self._children(root.id, q_end),
        }

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------

    def _project_teams(self, root, plan_ids: Sequence[str]) -> List[str]:
        """Команда проекта: поле задачи, иначе команда плана, иначе пусто."""
        if root.team:
            return [root.team]
        if plan_ids:
            from app.models import ResourcePlan

            teams = (
                self._db.execute(
                    select(ResourcePlan.team).where(ResourcePlan.id.in_(list(plan_ids)))
                )
                .scalars()
                .all()
            )
            return [t for t in dict.fromkeys(teams) if t]
        return []

    def _children(self, root_id: str, fact_until: date) -> List[dict]:
        """Прямые дети проекта; часы — по поддереву каждого ребёнка."""
        from app.models import Issue, Worklog

        rows = (
            self._db.query(Issue.id, Issue.key, Issue.summary, Issue.status)
            .filter(Issue.parent_id == root_id)
            .all()
        )
        if not rows:
            return []
        child_ids = [r.id for r in rows]
        sub = subtree_ids(self._db, child_ids)
        all_ids = {i for ids in sub.values() for i in ids}
        end_dt = datetime.combine(fact_until, time.max)
        hours_rows = (
            self._db.query(
                Worklog.issue_id,
                func.coalesce(func.sum(Worklog.hours), 0.0).label("hours"),
            )
            .filter(Worklog.issue_id.in_(all_ids), Worklog.started_at <= end_dt)
            .group_by(Worklog.issue_id)
            .all()
        )
        by_issue = {r.issue_id: float(r.hours or 0.0) for r in hours_rows}
        out = [
            {
                "key": r.key,
                "title": r.summary,
                "status": r.status,
                "jira_url": jira_url(r.key),
                "hours": round(sum(by_issue.get(i, 0.0) for i in sub.get(r.id, ())), 1),
            }
            for r in rows
        ]
        out.sort(key=lambda c: (-c["hours"], c["key"] or ""))
        return out

    def _timeline(
        self,
        plan_ids: Sequence[str],
        root_ids: Sequence[str],
        q_start: date,
        q_end: date,
    ) -> dict:
        """Полосы фаз по проектам. Шкала — от первой до последней даты назначений."""
        from app.models import BacklogItem, Issue, ResourcePlanAssignment

        rows: List[tuple] = []
        if plan_ids and root_ids:
            rows = (
                self._db.query(ResourcePlanAssignment, BacklogItem.issue_id, Issue.key,
                               Issue.summary, Issue.status)
                .join(BacklogItem, BacklogItem.id == ResourcePlanAssignment.backlog_item_id)
                .join(Issue, Issue.id == BacklogItem.issue_id)
                .filter(
                    ResourcePlanAssignment.plan_id.in_(list(plan_ids)),
                    BacklogItem.issue_id.in_(list(root_ids)),
                    ResourcePlanAssignment.start_date.is_not(None),
                    ResourcePlanAssignment.end_date.is_not(None),
                )
                .order_by(ResourcePlanAssignment.start_date)
                .all()
            )

        by_issue: Dict[str, dict] = {}
        starts: List[date] = []
        ends: List[date] = []
        for a, issue_id, key, summary, status in rows:
            row = by_issue.setdefault(
                issue_id, {"key": key, "title": summary, "status": status, "bars": []}
            )
            row["bars"].append(
                {
                    "phase": a.phase,
                    "label": PHASE_LABEL.get(a.phase, a.phase or "—"),
                    "start_date": a.start_date.isoformat(),
                    "end_date": a.end_date.isoformat(),
                }
            )
            starts.append(a.start_date)
            ends.append(a.end_date)

        return {
            "start": min(starts).isoformat() if starts else None,
            "end": max(ends).isoformat() if ends else None,
            "quarter_start": q_start.isoformat(),
            "quarter_end": q_end.isoformat(),
            "rows": list(by_issue.values()),
        }


# ----------------------------------------------------------------------
# Чистые функции
# ----------------------------------------------------------------------

def _pct(fact: float, plan: Optional[float]) -> Optional[int]:
    if plan is None or plan <= 0:
        return None
    return round(fact / plan * 100)


def _project_work_types(bd: dict) -> tuple[List[dict], Optional[float], float]:
    """Из разбивки — список видов работ + итоги. total_plan=None если плана нет."""
    work_types: List[dict] = []
    for role in DISPLAY_ROLES:
        plan = round(bd["plan"].get(role, 0.0), 1)
        fact = round(bd["fact"].get(role, 0.0), 1)
        work_types.append(
            {
                "code": role,
                "label": PHASE_LABEL[role],
                "plan_hours": plan,
                "fact_hours": fact,
                "pct": _pct(fact, plan),
            }
        )
    total_plan_raw = round(sum(w["plan_hours"] for w in work_types), 1)
    total_fact = round(sum(w["fact_hours"] for w in work_types), 1)
    return work_types, (total_plan_raw if total_plan_raw > 0 else None), total_fact
