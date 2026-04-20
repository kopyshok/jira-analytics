"""BacklogService — auto-population of BacklogItem from Issue with category
`initiatives_backlog`.

Jira — источник истины для задач-инициатив; локально не трогаются только
поля, которые PM заводит вручную: ``priority``, ``opo_analyst_ratio``,
``year``, ``quarter``, ``id``, ``created_at``.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, ScenarioAllocation


BACKLOG_CATEGORY = "initiatives_backlog"


def _get_default_quarter_year(db: Session) -> tuple[Optional[int], Optional[str]]:
    """Читает дефолтные year/quarter для новых BacklogItem из AppSetting."""
    from app.models import AppSetting

    year_row = db.query(AppSetting).filter_by(key="backlog_default_year").first()
    quarter_row = db.query(AppSetting).filter_by(key="backlog_default_quarter").first()
    y = (
        int(year_row.value)
        if year_row and year_row.value and year_row.value.isdigit()
        else None
    )
    q = quarter_row.value if quarter_row and quarter_row.value else None
    return y, q


class BacklogService:
    """Sync BacklogItem records to Issue.category.

    Caller controls the transaction: ``sync_from_issue`` делает ``flush()``,
    но не коммитит — окончательный commit должен сделать вызвавший код.

    Дефолтные year/quarter для новых BacklogItem читаются из AppSetting
    один раз в ``__init__`` и кешируются — это важно для batch-контекстов
    (``MappingService.recalculate_issues``, ``/refresh-from-jira``), где
    sync_from_issue вызывается десятками раз подряд.
    """

    def __init__(self, db: Session):
        self.db = db
        self._default_year, self._default_quarter = _get_default_quarter_year(db)

    def sync_from_issue(self, issue: Issue) -> Optional[BacklogItem]:
        """Идемпотентно выравнивает BacklogItem с Issue по текущей категории.

        - ``category == 'initiatives_backlog'`` — create-or-update, перетягивает
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
                # Дефолты только при создании — не перетираем то, что PM ввёл.
                existing.year = self._default_year
                existing.quarter = self._default_quarter
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
