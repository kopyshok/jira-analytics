"""Сервис определения категории задачи по иерархии и правилам.

Приоритет определения категории:
1. Явное переопределение задачи (CategoryOverride)
2. Ближайший настроенный корневой эпик/задача (ScopeRoot) — идём вверх по parent_id
3. Правила качества данных (применяются к worklog)
4. Категория «незаполненные / сомнительные worklog» (fallback)
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import (
    CategoryOverride,
    Issue,
    ScopeRoot,
    Worklog,
    WorklogQualityRule,
)
from app.services.categories import MappingSource, UNFILLED_WORKLOG_CODE


DEFAULT_MIN_COMMENT_LENGTH = 5
MIN_COMMENT_LENGTH_RULE_CODE = "min_comment_length"


@dataclass
class CategoryResolution:
    """Результат резолвинга категории для задачи или worklog."""

    category_code: str
    source: str  # MappingSource
    source_entity_key: Optional[str] = None  # Ключ задачи-источника (для scope_root)


class CategoryResolver:
    """Резолвер категории задачи.

    Кэширует scope_roots и overrides в памяти на время работы экземпляра,
    чтобы не ходить в БД за каждой задачей.
    """

    def __init__(self, db: Session):
        self.db = db
        self._overrides: dict[str, str] = {}          # jira_issue_key -> category_code
        self._roots_by_key: dict[str, str] = {}       # jira_issue_key -> category_code
        self._min_comment_length: int = DEFAULT_MIN_COMMENT_LENGTH
        self._loaded = False

    def _load_caches(self) -> None:
        """Загрузить scope_roots, category_overrides и worklog_quality_rules."""
        if self._loaded:
            return

        overrides = self.db.query(CategoryOverride).all()
        self._overrides = {o.jira_issue_key: o.category_code for o in overrides}

        roots = (
            self.db.query(ScopeRoot)
            .filter(ScopeRoot.is_enabled == True)  # noqa: E712
            .all()
        )
        self._roots_by_key = {r.jira_issue_key: r.category_code for r in roots}

        min_len_rule = (
            self.db.query(WorklogQualityRule)
            .filter(
                WorklogQualityRule.rule_code == MIN_COMMENT_LENGTH_RULE_CODE,
                WorklogQualityRule.is_enabled == True,  # noqa: E712
            )
            .first()
        )
        if min_len_rule and min_len_rule.threshold_value is not None:
            self._min_comment_length = int(min_len_rule.threshold_value)
        else:
            self._min_comment_length = DEFAULT_MIN_COMMENT_LENGTH

        self._loaded = True

    def resolve_for_issue(self, issue: Issue) -> CategoryResolution:
        """Определить категорию для задачи.

        Приоритет:
        1. assigned_category на самой задаче
        2. Ближайший предок с assigned_category (наследование)
        3. Явное переопределение (CategoryOverride)
        4. Scope root (walk up parent chain)
        5. Fallback
        """
        self._load_caches()

        # 1. Прямое назначение на задаче
        if issue.assigned_category:
            return CategoryResolution(
                category_code=issue.assigned_category,
                source=MappingSource.ASSIGNED,
                source_entity_key=issue.key,
            )

        # 2. Обход иерархии вверх
        current: Optional[Issue] = issue
        visited: set[str] = set()

        while current is not None and current.id not in visited:
            visited.add(current.id)

            # assigned_category на предке
            if current.id != issue.id and current.assigned_category:
                return CategoryResolution(
                    category_code=current.assigned_category,
                    source=MappingSource.ASSIGNED,
                    source_entity_key=current.key,
                )

            # Явное переопределение (category_overrides)
            if current.key in self._overrides:
                return CategoryResolution(
                    category_code=self._overrides[current.key],
                    source=MappingSource.OVERRIDE,
                    source_entity_key=current.key,
                )

            # Scope root
            if current.key in self._roots_by_key:
                return CategoryResolution(
                    category_code=self._roots_by_key[current.key],
                    source=MappingSource.SCOPE_ROOT,
                    source_entity_key=current.key,
                )

            # Идём к родителю
            if current.parent_id:
                current = self.db.get(Issue, current.parent_id)
            else:
                current = None

        # 3. Fallback — «незаполненные / сомнительные»
        return CategoryResolution(
            category_code=UNFILLED_WORKLOG_CODE,
            source=MappingSource.FALLBACK,
        )

    def resolve_inherited_for_issue(self, issue: Issue) -> CategoryResolution:
        """Категория, которую задача получает ОТ РОДИТЕЛЯ — без учёта своей
        назначенной категории. Используется для детекта значимого переезда.

        Если родителя нет — fallback-код (стабильная точка отсчёта).
        """
        self._load_caches()
        if not issue.parent_id:
            return CategoryResolution(
                category_code=UNFILLED_WORKLOG_CODE,
                source=MappingSource.FALLBACK,
            )
        parent = self.db.get(Issue, issue.parent_id)
        if parent is None:
            return CategoryResolution(
                category_code=UNFILLED_WORKLOG_CODE,
                source=MappingSource.FALLBACK,
            )
        return self.resolve_for_issue(parent)

    def resolve_for_worklog(
        self,
        worklog: Worklog,
        min_comment_length: Optional[int] = None,
    ) -> CategoryResolution:
        """Определить категорию для worklog.

        Сначала применяет правила качества: если комментарий отсутствует
        или слишком короткий, worklog попадает в «сомнительные».
        Иначе использует категорию задачи.

        Порог длины комментария берётся из таблицы ``worklog_quality_rules``
        (rule_code=``min_comment_length``). Аргумент ``min_comment_length``
        оставлен как override для тестов и вызовов ad-hoc.
        """
        self._load_caches()

        threshold = (
            min_comment_length
            if min_comment_length is not None
            else self._min_comment_length
        )

        # Правило качества: пустой или слишком короткий комментарий
        comment = (worklog.comment_text or "").strip()
        if len(comment) < threshold:
            return CategoryResolution(
                category_code=UNFILLED_WORKLOG_CODE,
                source=MappingSource.QUALITY_RULE,
            )

        # Иначе — категория задачи
        if worklog.issue:
            return self.resolve_for_issue(worklog.issue)

        return CategoryResolution(
            category_code=UNFILLED_WORKLOG_CODE,
            source=MappingSource.FALLBACK,
        )


def reset_parent_context(
    resolver_db,
    issue: "Issue",
    resolver: "CategoryResolver",
) -> None:
    """Сбросить пометку переезда и сдвинуть точку отсчёта на текущий контекст.

    Вызывается из всех точек подтверждения категории: после подтверждения
    «откуда / была» больше не актуально, новая база = текущая категория от
    родителя.
    """
    from app.models import Issue as _Issue

    issue.parent_changed = False
    issue.category_context = resolver.resolve_inherited_for_issue(issue).category_code
    parent = resolver_db.get(_Issue, issue.parent_id) if issue.parent_id else None
    issue.category_context_key = parent.key if parent else None


def effective_category_with_ancestors(
    resolver: "CategoryResolver",
    issue: "Issue",
    pending: dict[str, str | None],
) -> str | None:
    """Вернуть эффективную категорию задачи: pending override → own assigned → ближайший
    предок с assigned_category. Используется server-side для tab-routing задач.

    pending — клиентский патч {issue_id: category_code | None}. Передаётся
    фронтом в запрос tree/roots, чтобы клик «Сохранить» не требовал refetch.
    """
    from app.models import Issue
    sess = resolver.db

    if issue.id in pending:
        own = pending[issue.id]
        if own is not None:
            return own

    if not (issue.category_verified or False):
        return None

    if issue.assigned_category:
        return issue.assigned_category

    current_parent_id = issue.parent_id
    for _ in range(20):
        if not current_parent_id:
            return None
        if current_parent_id in pending:
            pcode = pending[current_parent_id]
            if pcode is not None:
                return pcode
        parent = sess.get(Issue, current_parent_id)
        if not parent:
            return None
        if parent.assigned_category:
            return parent.assigned_category
        current_parent_id = parent.parent_id
    return None
