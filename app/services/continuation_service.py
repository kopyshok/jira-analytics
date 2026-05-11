"""Расчёт «уже списано» по issue до начала квартала сценария и флага продолжения.

Per-scenario batch: один запрос за allocations + один за worklogs (по списку
issue_ids) — без N+1.

Категория ворклога определяется по ``Issue.assigned_category`` (модель
``Worklog`` не хранит собственной категории). Маппинг category code → role
описан в ``CATEGORY_TO_ROLE`` ниже; ворклоги с неизвестной/пустой категорией
не учитываются.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session, joinedload

from app.models import (
    BacklogItem,
    Issue,
    PlanningScenario,
    ScenarioAllocation,
    Worklog,
)

# Маппинг category code → role-bucket для агрегации ворклогов.
# Покрывает seeded categories из миграции 006 + типичные коды развития/тестирования/ОПЭ.
CATEGORY_TO_ROLE: dict[str, str] = {
    # Аналитика
    "analysis": "analyst",
    "business_analysis": "analyst",
    "consult": "analyst",
    "support_consultation": "analyst",
    # Разработка
    "development": "dev",
    "tech_debt": "dev",
    # Тестирование
    "testing": "qa",
    # ОПЭ — опытно-промышленная эксплуатация (закрывает аналитик+разработчик).
    "ope": "opo",
    "ope_analysis": "opo",
    "ope_development": "opo",
}

_QUARTER_TO_MONTH = {1: 1, 2: 4, 3: 7, 4: 10}


def _parse_quarter(q) -> int:
    """'Q1'/'Q2'/'1'/'2'/int → 1..4."""
    if isinstance(q, int):
        return q
    s = str(q).upper().replace("Q", "").strip()
    return int(s)


def _quarter_start(year: int, quarter) -> date:
    q = _parse_quarter(quarter)
    return date(year, _QUARTER_TO_MONTH[q], 1)


def _empty_spent() -> dict[str, float]:
    return {"analyst": 0.0, "dev": 0.0, "qa": 0.0, "opo": 0.0}


class ContinuationService:
    """Считает «уже списано» по ролям и флаг продолжения для всех allocations сценария."""

    def __init__(self, db: Session):
        self.db = db

    def compute_for_scenario(self, scenario_id: str) -> Dict[str, dict]:
        """Возвращает map ``{allocation_id: {spent, spent_total, is_continuation, jira_estimate}}``.

        Если сценарий не найден или у него нет year/quarter — возвращает пустой dict.
        """
        scenario = self.db.get(PlanningScenario, scenario_id)
        if scenario is None or scenario.year is None or scenario.quarter is None:
            return {}

        q_start = _quarter_start(scenario.year, scenario.quarter)
        q_start_dt = datetime.combine(q_start, datetime.min.time())

        allocations = (
            self.db.query(ScenarioAllocation)
            .options(joinedload(ScenarioAllocation.backlog_item))
            .filter(ScenarioAllocation.scenario_id == scenario_id)
            .all()
        )

        root_issue_ids = [
            a.backlog_item.issue_id
            for a in allocations
            if a.backlog_item is not None and a.backlog_item.issue_id is not None
        ]

        # Разворачиваем поддерево каждого корня вниз по Issue.parent_id.
        # Ворклоги, как правило, лежат на детях Initiative — не на самом
        # Initiative-issue. root_by_descendant: id потомка → id корня, чтобы
        # атрибутировать spent правильной allocation.
        root_by_descendant: dict[str, str] = {rid: rid for rid in root_issue_ids}
        if root_issue_ids:
            CHUNK = 500  # SQLite IN-limit guard, как в analytics_service
            frontier = list(set(root_issue_ids))
            while frontier:
                new_pairs: list[tuple[str, str]] = []
                for i in range(0, len(frontier), CHUNK):
                    chunk = frontier[i : i + CHUNK]
                    children = (
                        self.db.query(Issue.id, Issue.parent_id)
                        .filter(Issue.parent_id.in_(chunk))
                        .all()
                    )
                    for child_id, parent_id in children:
                        if child_id in root_by_descendant:
                            continue
                        root_by_descendant[child_id] = root_by_descendant[parent_id]
                        new_pairs.append((child_id, parent_id))
                frontier = [cid for cid, _ in new_pairs]

        spent_by_root: dict[str, dict[str, float]] = {}
        if root_by_descendant:
            descendant_ids = list(root_by_descendant.keys())
            worklogs: list[Worklog] = []
            for i in range(0, len(descendant_ids), 500):
                chunk = descendant_ids[i : i + 500]
                worklogs.extend(
                    self.db.query(Worklog)
                    .options(joinedload(Worklog.issue))
                    .filter(
                        Worklog.issue_id.in_(chunk),
                        Worklog.started_at < q_start_dt,
                    )
                    .all()
                )
            for w in worklogs:
                root_id = root_by_descendant.get(w.issue_id)
                if root_id is None:
                    continue
                cat_code: Optional[str] = None
                if w.issue is not None:
                    cat_code = w.issue.assigned_category or w.issue.category
                role = CATEGORY_TO_ROLE.get(cat_code or "")
                if role is None:
                    continue
                bucket = spent_by_root.setdefault(root_id, _empty_spent())
                bucket[role] += float(w.hours or 0.0)

        result: Dict[str, dict] = {}
        for a in allocations:
            bi: Optional[BacklogItem] = a.backlog_item
            if bi is None or bi.issue_id is None:
                spent = _empty_spent()
            else:
                spent = spent_by_root.get(bi.issue_id, _empty_spent())
            spent_total = sum(spent.values())
            jira_est = {
                "analyst": float(bi.estimate_analyst_hours or 0.0) if bi else 0.0,
                "dev": float(bi.estimate_dev_hours or 0.0) if bi else 0.0,
                "qa": float(bi.estimate_qa_hours or 0.0) if bi else 0.0,
                "opo": float(bi.estimate_opo_hours or 0.0) if bi else 0.0,
            }
            result[a.id] = {
                "spent": spent,
                "spent_total": spent_total,
                "is_continuation": spent_total > 0,
                "jira_estimate": jira_est,
            }
        return result
