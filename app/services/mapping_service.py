"""Сервис массового пересчёта категорий.

Применяет правила резолвинга ко всем задачам и worklog,
обновляет denormalized поле Issue.category и таблицу category_mappings.
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Issue, Worklog, CategoryMapping
from app.repositories.base import BaseRepository
from app.services.backlog_service import BacklogService
from app.services.category_resolver import CategoryResolver


logger = logging.getLogger("jira_analytics.mapping")


class MappingStats:
    """Статистика пересчёта мэппинга."""

    def __init__(self):
        self.issues_processed = 0
        self.worklogs_processed = 0
        self.mappings_created = 0
        self.mappings_updated = 0
        self.started_at = datetime.utcnow()
        self.finished_at: Optional[datetime] = None

    def finish(self):
        self.finished_at = datetime.utcnow()

    @property
    def duration_seconds(self) -> float:
        end = self.finished_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        return {
            "issues_processed": self.issues_processed,
            "worklogs_processed": self.worklogs_processed,
            "mappings_created": self.mappings_created,
            "mappings_updated": self.mappings_updated,
            "duration_seconds": self.duration_seconds,
        }


class MappingService:
    """Сервис пересчёта категорий для задач и worklog."""

    def __init__(self, db: Session):
        self.db = db
        self.resolver = CategoryResolver(db)
        self.mapping_repo = BaseRepository(CategoryMapping, db)
        self.stats = MappingStats()

    def _upsert_mapping(
        self,
        entity_type: str,
        entity_id: str,
        category: str,
        source_rule: str,
        cache: Optional[dict] = None,
    ) -> None:
        """Создать или обновить запись в category_mappings.

        ``cache`` — опциональный pre-fetched dict ``{(type, entity_id): mapping}``,
        используется в bulk-recalc чтобы избежать N+1 SELECT на 100k+ задач.
        Новые записи автоматически добавляются в cache.
        """
        if cache is not None:
            existing = cache.get((entity_type, entity_id))
        else:
            existing = (
                self.db.query(CategoryMapping)
                .filter(
                    CategoryMapping.entity_type == entity_type,
                    CategoryMapping.entity_id == entity_id,
                )
                .one_or_none()
            )

        if existing:
            if (
                existing.category != category
                or existing.source_rule != source_rule
            ):
                existing.category = category
                existing.source_rule = source_rule
                self.stats.mappings_updated += 1
        else:
            mapping = CategoryMapping(
                entity_type=entity_type,
                entity_id=entity_id,
                category=category,
                source_rule=source_rule,
            )
            self.db.add(mapping)
            self.stats.mappings_created += 1
            if cache is not None:
                cache[(entity_type, entity_id)] = mapping

    def recalculate_issues(self) -> int:
        """Пересчитать категории всех задач.

        Обновляет denormalized поле Issue.category и category_mappings.
        Для задач, у которых категория РЕАЛЬНО поменялась, дополнительно
        вызывает ``BacklogService.sync_from_issue`` — это гарантирует, что
        после полного Jira-синка бэклог автоматически приводится в
        соответствие с новыми категориями (создаются BacklogItem для
        новых ``initiatives_rfa``, удаляются для ушедших).

        Note: per изменённую задачу sync_from_issue добавляет 1-3 запроса
        (O(N) extra queries в худшем случае). Для MVP это ОК; при большом
        количестве задач потребуется оптимизация (batch-вариант).
        """
        logger.info("Recalculating categories for all issues...")

        issues = self.db.query(Issue).all()
        # Bulk-prefetch existing mappings — устраняет N SELECT в _upsert_mapping
        # на 100k+ задач (главная причина 130s+ recalc на полном бэклоге).
        mapping_cache: dict = {
            (m.entity_type, m.entity_id): m
            for m in self.db.query(CategoryMapping)
            .filter(CategoryMapping.entity_type == "issue")
            .all()
        }
        count = 0
        backlog = BacklogService(self.db)

        for issue in issues:
            resolution = self.resolver.resolve_for_issue(issue)

            # Обновляем denormalized поле
            category_changed = issue.category != resolution.category_code
            if category_changed:
                issue.category = resolution.category_code

            # Обновляем category_mappings
            self._upsert_mapping(
                entity_type="issue",
                entity_id=issue.id,
                category=resolution.category_code,
                source_rule=resolution.source,
                cache=mapping_cache,
            )

            # Синкаем BacklogItem только для реально изменившихся задач —
            # экономим N*M запросов для остального большинства.
            if category_changed:
                backlog.sync_from_issue(issue)

            count += 1
            if count % 100 == 0:
                self.db.flush()
                logger.debug(f"Processed {count}/{len(issues)} issues")

        self.stats.issues_processed = count
        self.db.commit()
        logger.info(f"Issue categories recalculated: {count}")
        return count

    def recalculate_worklogs(self) -> int:
        """Пересчитать категории для worklog.

        Применяет правила качества к каждому worklog
        и создаёт записи в category_mappings.
        """
        logger.info("Recalculating categories for worklogs...")

        worklogs = self.db.query(Worklog).all()
        mapping_cache: dict = {
            (m.entity_type, m.entity_id): m
            for m in self.db.query(CategoryMapping)
            .filter(CategoryMapping.entity_type == "worklog")
            .all()
        }
        count = 0

        for worklog in worklogs:
            resolution = self.resolver.resolve_for_worklog(worklog)

            self._upsert_mapping(
                entity_type="worklog",
                entity_id=worklog.id,
                category=resolution.category_code,
                source_rule=resolution.source,
                cache=mapping_cache,
            )

            count += 1
            if count % 200 == 0:
                self.db.flush()
                logger.debug(f"Processed {count}/{len(worklogs)} worklogs")

        self.stats.worklogs_processed = count
        self.db.commit()
        logger.info(f"Worklog categories recalculated: {count}")
        return count

    def recalculate_for_issues(self, issue_ids: list[str]) -> int:
        """Пересчитать категории только для указанных issue_ids.

        Возвращает количество затронутых issues. Используется team-mode pipeline,
        чтобы не гонять полный recalculate_all для пары сотен задач.
        """
        if not issue_ids:
            return 0
        issues = self.db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
        affected = 0
        backlog = BacklogService(self.db)
        for issue in issues:
            resolution = self.resolver.resolve_for_issue(issue)
            category_changed = issue.category != resolution.category_code
            if category_changed:
                issue.category = resolution.category_code
                backlog.sync_from_issue(issue)
                affected += 1
            self._upsert_mapping(
                entity_type="issue",
                entity_id=issue.id,
                category=resolution.category_code,
                source_rule=resolution.source,
            )
        self.db.commit()
        return affected

    def recalculate_all(self) -> MappingStats:
        """Полный пересчёт: сначала задачи, затем worklog.

        Важно пересчитывать в этом порядке, т.к. worklog категория
        может зависеть от категории задачи.
        """
        logger.info("Starting full mapping recalculation...")
        self.stats = MappingStats()

        try:
            self.recalculate_issues()
            self.recalculate_worklogs()
        finally:
            self.stats.finish()

        logger.info(f"Mapping recalculation complete in {self.stats.duration_seconds:.1f}s")
        return self.stats
