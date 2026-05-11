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

        issue_ids = [
            a.backlog_item.issue_id
            for a in allocations
            if a.backlog_item is not None and a.backlog_item.issue_id is not None
        ]

        spent_by_issue: dict[str, dict[str, float]] = {}
        if issue_ids:
            worklogs = (
                self.db.query(Worklog)
                .options(joinedload(Worklog.issue))
                .filter(
                    Worklog.issue_id.in_(issue_ids),
                    Worklog.started_at < q_start_dt,
                )
                .all()
            )
            for w in worklogs:
                bucket = spent_by_issue.setdefault(w.issue_id, _empty_spent())
                cat_code: Optional[str] = None
                if w.issue is not None:
                    cat_code = w.issue.assigned_category or w.issue.category
                role = CATEGORY_TO_ROLE.get(cat_code or "")
                if role is None:
                    continue
                bucket[role] += float(w.hours or 0.0)

        result: Dict[str, dict] = {}
        for a in allocations:
            bi: Optional[BacklogItem] = a.backlog_item
            if bi is None or bi.issue_id is None:
                spent = _empty_spent()
            else:
                spent = spent_by_issue.get(bi.issue_id, _empty_spent())
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
