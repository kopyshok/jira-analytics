"""BacklogService — auto-population of BacklogItem from Issue with category
`initiatives_rfa` («Инициативы и RFA»).

Бэклог — пул всех задач-инициатив без привязки к кварталу. Квартальный
план собирается в сценариях отметками по элементам бэклога.

Jira — источник истины для задач-инициатив; локально не трогаются только
поля, которые PM заводит вручную: ``priority``, ``opo_analyst_ratio``,
``id``, ``created_at``.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, ScenarioAllocation


BACKLOG_CATEGORY = "initiatives_rfa"


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
          заголовок/проект/плановые оценки из Issue.
        - Иначе: если BacklogItem существует и не используется ни в одном
          сценарии — удаляем. Если используется — soft-unlink
          (``issue_id = NULL``), запись остаётся, чтобы не сломать сценарий.
        """
        existing = (
            self.db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        )

        if issue.category == BACKLOG_CATEGORY:
            if existing is None:
                existing = BacklogItem(issue_id=issue.id)
                self.db.add(existing)
                existing.opo_analyst_ratio = 0.5
            # Jira-sourced поля — перезаписываем всегда.
            existing.title = issue.summary
            existing.project_id = issue.project_id
            existing.estimate_analyst_hours = issue.planned_analyst_hours
            existing.estimate_dev_hours = issue.planned_dev_hours
            existing.estimate_qa_hours = issue.planned_qa_hours
            existing.estimate_opo_hours = issue.planned_opo_hours
            existing.impact = issue.impact
            existing.risk = issue.risk
            # Derived aggregate.
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
            self.db.flush()
            return existing

        # Category no longer matches — cleanup.
        if existing is None:
            return None
        has_alloc = (
            self.db.query(ScenarioAllocation)
            .filter_by(backlog_item_id=existing.id)
            .first()
            is not None
        )
        if has_alloc:
            existing.issue_id = None
            self.db.flush()
        else:
            self.db.delete(existing)
            self.db.flush()
        return None
