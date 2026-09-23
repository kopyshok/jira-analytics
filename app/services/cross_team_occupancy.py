"""Занятость сотрудников в планах других команд.

Опорный план команды на квартал — тот, по которому остальные команды видят,
когда её люди заняты: основной (иначе «Готово», иначе самый свежий) план
утверждённого сценария; нет утверждённого — план самого свежего черновика
с признаком «предварительно». Копии-форки не участвуют.

Все функции — чистое чтение, без commit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlanningScenario, ResourcePlan
from app.services.plan_common import _plan_sort_key, _quarter_variants


@dataclass(frozen=True)
class ReferencePlan:
    """Опорный план команды на квартал."""

    plan_id: str
    team: str
    provisional: bool


def quarter_num(value) -> Optional[int]:
    """«Q3» / «3» / 3 → 3; мусор → None."""
    try:
        q = int(str(value or "").strip().upper().lstrip("Q"))
    except ValueError:
        return None
    return q if 1 <= q <= 4 else None


def _ref_key(plan: ResourcePlan) -> tuple:
    """Порядок выбора внутри сценариев: основной → «Готово» → свежесть."""
    return (bool(plan.is_baseline), plan.status == "ready", _plan_sort_key(plan))


def reference_plans(
    db: Session,
    year: int,
    quarter: int,
    exclude_team: Optional[str] = None,
) -> Dict[str, ReferencePlan]:
    """Опорные планы всех команд квартала: {команда: ReferencePlan}.

    Один запрос. ``exclude_team`` — команда, чей собственный план не должен
    считаться «чужой» занятостью.
    """
    rows = db.execute(
        select(ResourcePlan, PlanningScenario)
        .join(PlanningScenario, PlanningScenario.id == ResourcePlan.scenario_id)
        .where(
            ResourcePlan.year == year,
            ResourcePlan.quarter.in_(_quarter_variants(quarter)),
            ResourcePlan.parent_plan_id.is_(None),
            ResourcePlan.team.is_not(None),
            PlanningScenario.status.in_(("approved", "draft")),
        )
    ).all()

    approved: Dict[str, list] = defaultdict(list)
    drafts: Dict[str, list] = defaultdict(list)
    for plan, sc in rows:
        if exclude_team is not None and plan.team == exclude_team:
            continue
        bucket = approved if sc.status == "approved" else drafts
        bucket[plan.team].append((plan, sc))

    out: Dict[str, ReferencePlan] = {}
    for team in set(approved) | set(drafts):
        if approved.get(team):
            best = max((p for p, _ in approved[team]), key=_ref_key)
            out[team] = ReferencePlan(best.id, team, False)
            continue
        fresh_sc = max(
            (sc for _, sc in drafts[team]),
            key=lambda s: (s.updated_at or s.created_at or datetime.min, s.id),
        )
        best = max(
            (p for p, sc in drafts[team] if sc.id == fresh_sc.id), key=_ref_key
        )
        out[team] = ReferencePlan(best.id, team, True)
    return out
