"""Сервис аналитики факта — агрегаты по worklog.

Отчёты:
- Часы по сотрудникам
- Часы по проектам
- Часы по категориям
- Часы по периодам (день/неделя/месяц)
- Контекстные переключения (сколько раз сотрудник переключался между проектами)
"""

from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional

from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models import Worklog, Issue, Employee, Project, CategoryMapping
from app.services.categories import CATEGORY_LABELS, get_category_labels


@dataclass
class AggregateRow:
    """Строка агрегированного отчёта."""

    key: str               # ID или код сущности
    label: str             # Отображаемое имя
    total_hours: float
    worklog_count: int


@dataclass
class ContextSwitchRow:
    """Метрика контекстных переключений по сотруднику."""

    employee_id: str
    employee_name: str
    total_worklogs: int
    distinct_projects: int
    distinct_categories: int
    switches: int  # Количество смен проекта в хронологической последовательности


class AnalyticsService:
    """Сервис аналитики факта по worklog."""

    def __init__(self, db: Session):
        self.db = db

    def _apply_date_filter(self, query, start: Optional[datetime], end: Optional[datetime]):
        """Применить фильтр по периоду к запросу Worklog."""
        if start:
            query = query.filter(Worklog.started_at >= start)
        if end:
            query = query.filter(Worklog.started_at <= end)
        return query

    @staticmethod
    def _exclude_non_analysis(query):
        """Исключить задачи с include_in_analysis=False (join Issue уже должен быть)."""
        return query.filter(Issue.include_in_analysis != False)  # noqa: E712

    # === Агрегаты ===

    def hours_by_employee(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> list[AggregateRow]:
        """Часы по сотрудникам за период."""
        query = (
            self.db.query(
                Employee.id.label("key"),
                Employee.display_name.label("label"),
                func.sum(Worklog.hours).label("total_hours"),
                func.count(Worklog.id).label("cnt"),
            )
            .join(Worklog, Worklog.employee_id == Employee.id)
            .group_by(Employee.id, Employee.display_name)
            .order_by(func.sum(Worklog.hours).desc())
        )
        query = self._apply_date_filter(query, start, end)
        if employee_id:
            query = query.filter(Worklog.employee_id == employee_id)
        if project_key:
            query = (
                query
                .join(Issue, Worklog.issue_id == Issue.id)
                .join(Project, Issue.project_id == Project.id)
                .filter(Project.key == project_key)
            )

        return [
            AggregateRow(
                key=row.key,
                label=row.label,
                total_hours=float(row.total_hours or 0),
                worklog_count=int(row.cnt),
            )
            for row in query.all()
        ]

    def hours_by_project(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> list[AggregateRow]:
        """Часы по проектам за период."""
        query = (
            self.db.query(
                Project.id.label("key"),
                Project.name.label("label"),
                func.sum(Worklog.hours).label("total_hours"),
                func.count(Worklog.id).label("cnt"),
            )
            .join(Issue, Issue.project_id == Project.id)
            .join(Worklog, Worklog.issue_id == Issue.id)
            .group_by(Project.id, Project.name)
            .order_by(func.sum(Worklog.hours).desc())
        )
        query = self._apply_date_filter(query, start, end)
        if employee_id:
            query = query.filter(Worklog.employee_id == employee_id)
        if project_key:
            query = query.filter(Project.key == project_key)

        return [
            AggregateRow(
                key=row.key,
                label=row.label,
                total_hours=float(row.total_hours or 0),
                worklog_count=int(row.cnt),
            )
            for row in query.all()
        ]

    def hours_by_category(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> list[AggregateRow]:
        """Часы по категориям за период.

        Использует category_mappings для worklog (entity_type='worklog').
        Worklog без мэппинга попадает в 'unfilled_worklog'.
        """
        query = (
            self.db.query(
                CategoryMapping.category.label("category"),
                func.sum(Worklog.hours).label("total_hours"),
                func.count(Worklog.id).label("cnt"),
            )
            .join(
                CategoryMapping,
                and_(
                    CategoryMapping.entity_type == "worklog",
                    CategoryMapping.entity_id == Worklog.id,
                ),
            )
            .group_by(CategoryMapping.category)
            .order_by(func.sum(Worklog.hours).desc())
        )
        query = self._apply_date_filter(query, start, end)
        if employee_id:
            query = query.filter(Worklog.employee_id == employee_id)
        if project_key:
            query = (
                query
                .join(Issue, Worklog.issue_id == Issue.id)
                .join(Project, Issue.project_id == Project.id)
                .filter(Project.key == project_key)
            )

        return [
            AggregateRow(
                key=row.category,
                label=get_category_labels(self.db).get(row.category, row.category),
                total_hours=float(row.total_hours or 0),
                worklog_count=int(row.cnt),
            )
            for row in query.all()
        ]

    def hours_by_period(
        self,
        period: str = "day",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> list[AggregateRow]:
        """Часы по периодам: day, week, month.

        Группировка выполняется в Python: тянем сырые ``started_at`` и
        агрегируем. Так сервис остаётся независимым от диалекта БД
        (в SQLite нет ``date_trunc``, в PostgreSQL — нет ``strftime``).
        """
        query = self.db.query(Worklog.started_at, Worklog.hours)
        query = self._apply_date_filter(query, start, end)
        if employee_id:
            query = query.filter(Worklog.employee_id == employee_id)
        if project_key:
            query = (
                query
                .join(Issue, Worklog.issue_id == Issue.id)
                .join(Project, Issue.project_id == Project.id)
                .filter(Project.key == project_key)
            )

        buckets: dict[str, list[float]] = {}
        for started_at, hours in query.all():
            if started_at is None:
                continue
            key = self._period_key(started_at, period)
            buckets.setdefault(key, []).append(float(hours or 0))

        rows = [
            AggregateRow(
                key=key,
                label=key,
                total_hours=sum(values),
                worklog_count=len(values),
            )
            for key, values in buckets.items()
        ]
        rows.sort(key=lambda r: r.key)
        return rows

    @staticmethod
    def _period_key(ts: datetime, period: str) -> str:
        """Ключ группировки для даты по периоду day/week/month."""
        if period == "month":
            return f"{ts.year:04d}-{ts.month:02d}"
        if period == "week":
            iso_year, iso_week, _ = ts.isocalendar()
            return f"{iso_year:04d}-W{iso_week:02d}"
        return f"{ts.year:04d}-{ts.month:02d}-{ts.day:02d}"

    # === Контекстные переключения ===

    def context_switching(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
    ) -> list[ContextSwitchRow]:
        """Метрика контекстных переключений.

        Для каждого сотрудника считает:
        - Количество уникальных проектов
        - Количество уникальных категорий (из category_mappings)
        - Количество переключений проекта в хронологическом порядке worklog
        """
        query = (
            self.db.query(Worklog, Issue, Employee)
            .join(Issue, Worklog.issue_id == Issue.id)
            .join(Employee, Worklog.employee_id == Employee.id)
            .order_by(Worklog.employee_id, Worklog.started_at)
        )
        query = self._apply_date_filter(query, start, end)
        if employee_id:
            query = query.filter(Worklog.employee_id == employee_id)
        if project_key:
            query = (
                query
                .join(Project, Issue.project_id == Project.id)
                .filter(Project.key == project_key)
            )

        # category_mappings для worklog загружаем одним запросом
        mapping_rows = (
            self.db.query(CategoryMapping.entity_id, CategoryMapping.category)
            .filter(CategoryMapping.entity_type == "worklog")
            .all()
        )
        category_by_worklog: dict[str, str] = dict(mapping_rows)

        stats: dict[str, dict] = {}

        for worklog, issue, employee in query.all():
            emp_stats = stats.setdefault(
                employee.id,
                {
                    "employee_name": employee.display_name,
                    "total_worklogs": 0,
                    "projects": set(),
                    "categories": set(),
                    "switches": 0,
                    "last_project_id": None,
                },
            )

            emp_stats["total_worklogs"] += 1
            emp_stats["projects"].add(issue.project_id)

            category = category_by_worklog.get(worklog.id)
            if category:
                emp_stats["categories"].add(category)

            last_project = emp_stats["last_project_id"]
            if last_project is not None and last_project != issue.project_id:
                emp_stats["switches"] += 1
            emp_stats["last_project_id"] = issue.project_id

        return [
            ContextSwitchRow(
                employee_id=emp_id,
                employee_name=s["employee_name"],
                total_worklogs=s["total_worklogs"],
                distinct_projects=len(s["projects"]),
                distinct_categories=len(s["categories"]),
                switches=s["switches"],
            )
            for emp_id, s in sorted(
                stats.items(),
                key=lambda kv: kv[1]["switches"],
                reverse=True,
            )
        ]
