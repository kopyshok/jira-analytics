"""BacklogService — auto-population of BacklogItem from Issue with category
`initiatives_rfa` («Инициативы и RFA»).

Бэклог — пул всех задач-инициатив без привязки к кварталу. Квартальный
план собирается в сценариях отметками по элементам бэклога.

Jira — источник истины для задач-инициатив; локально не трогаются только
поля, которые PM заводит вручную: ``priority``, ``opo_analyst_ratio``,
``id``, ``created_at``.

Автосинк черновых сценариев: при создании/разархивации BacklogItem
в каждом draft-сценарии появляется ScenarioAllocation с дефолтами
(``included_flag=False``, ``planned_hours=0``); при архивации
BacklogItem allocations в draft-сценариях удаляются. Утверждённые
сценарии не трогаются.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, PlanningScenario, ScenarioAllocation


BACKLOG_CATEGORY = "initiatives_rfa"
QUARTERLY_TASKS_CATEGORY = "quarterly_tasks"
TRACKED_CATEGORIES = {BACKLOG_CATEGORY, QUARTERLY_TASKS_CATEGORY}


class BacklogService:
    """Sync BacklogItem records to Issue.category.

    Caller controls the transaction: ``sync_from_issue`` делает ``flush()``,
    но не коммитит — окончательный commit должен сделать вызвавший код.
    """

    def __init__(self, db: Session):
        self.db = db

    def sync_from_issue(self, issue: Issue) -> Optional[BacklogItem]:
        """Идемпотентно выравнивает BacklogItem с Issue по текущей категории.

        - ``category == 'initiatives_rfa'`` — create-or-update, перетягивает
          Jira-поля и сбрасывает ``archived_at`` (auto-restore). При создании
          или разархивации — допроставляет allocations в draft-сценариях.
        - Иначе: если BacklogItem существует — проставляем ``archived_at=now()``
          и удаляем allocations из draft-сценариев (утверждённые — не трогаем).
          Если BacklogItem нет — ничего не делаем.
        """
        existing = (
            self.db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        )

        if issue.category in TRACKED_CATEGORIES:
            is_new = existing is None
            was_archived = existing is not None and existing.archived_at is not None
            if is_new:
                existing = BacklogItem(issue_id=issue.id)
                self.db.add(existing)
                existing.opo_analyst_ratio = 0.5
            existing.title = issue.summary
            existing.project_id = issue.project_id
            existing.estimate_analyst_hours = issue.planned_analyst_hours
            existing.estimate_dev_hours = issue.planned_dev_hours
            existing.estimate_qa_hours = issue.planned_qa_hours
            existing.estimate_opo_hours = issue.planned_opo_hours
            existing.impact = issue.impact
            existing.risk = issue.risk
            total = sum(
                v or 0
                for v in (
                    existing.estimate_analyst_hours,
                    existing.estimate_dev_hours,
                    existing.estimate_qa_hours,
                    existing.estimate_opo_hours,
                )
            )
            existing.estimate_hours = total or None
            existing.archived_at = None
            self.db.flush()
            if is_new or was_archived:
                self._ensure_draft_allocations(existing.id)
            return existing

        # Category left backlog.
        if existing is None:
            return None
        if existing.archived_at is None:
            existing.archived_at = datetime.utcnow()
            self.db.flush()
            self._remove_draft_allocations(existing.id)
        return None

    def _ensure_draft_allocations(self, item_id: str) -> None:
        """В каждом draft-сценарии, где нет allocation на этот элемент — добить.

        Идемпотентно: существующие allocation (например, с проставленными PM
        ``included_flag`` и ``planned_hours``) не трогаем.
        """
        draft_scenario_ids = [
            sid
            for (sid,) in self.db.query(PlanningScenario.id)
            .filter(PlanningScenario.status == "draft")
            .all()
        ]
        if not draft_scenario_ids:
            return
        existing_scenario_ids = {
            sid
            for (sid,) in self.db.query(ScenarioAllocation.scenario_id)
            .filter(ScenarioAllocation.backlog_item_id == item_id)
            .all()
        }
        for sid in draft_scenario_ids:
            if sid in existing_scenario_ids:
                continue
            self.db.add(
                ScenarioAllocation(
                    scenario_id=sid,
                    backlog_item_id=item_id,
                    included_flag=False,
                    planned_hours=0,
                )
            )
        self.db.flush()

    def _remove_draft_allocations(self, item_id: str) -> None:
        """Удалить allocations на этот элемент из всех draft-сценариев.

        Утверждённые сценарии не трогаем — у них уже зафиксирован состав.
        """
        draft_scenario_ids = [
            sid
            for (sid,) in self.db.query(PlanningScenario.id)
            .filter(PlanningScenario.status == "draft")
            .all()
        ]
        if not draft_scenario_ids:
            return
        self.db.query(ScenarioAllocation).filter(
            ScenarioAllocation.backlog_item_id == item_id,
            ScenarioAllocation.scenario_id.in_(draft_scenario_ids),
        ).delete(synchronize_session=False)
        self.db.flush()
