"""ProjectsService — агрегаты по проектам (quarterly_tasks / archive_target).

list_projects()      — список проектов с метриками для левой панели.
get_project_detail() — полная агрегация для правой панели.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.issue import Issue
from app.models.worklog import Worklog
from app.models.employee import Employee
from app.models.category import Category

# Категории, у которых верхний issue считается «проектом».
PROJECT_CATEGORY_CODES = ("quarterly_tasks", "archive_target")


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ProjectListItem:
    """Элемент списка проектов (левая панель)."""
    id: str
    key: str
    summary: str
    status: str
    status_category: Optional[str]
    category: str
    total_hours: float
    child_count: int
    employee_count: int
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    rating_quality: Optional[int]
    rating_speed: Optional[int]
    rating_result: Optional[int]
    goals: Optional[str]
    planned_start_date: Optional[datetime]
    planned_end_date: Optional[datetime]


@dataclass
class CategoryBreakdown:
    """Разбивка часов по одной категории."""
    code: str
    label: str
    color: Optional[str]
    hours: float


@dataclass
class EmployeeBreakdown:
    """Разбивка часов по одному сотруднику."""
    employee_id: str
    name: str
    team: Optional[str]
    hours: float


@dataclass
class TopIssue:
    """Задача из поддерева с наибольшим количеством часов."""
    issue_id: str
    key: str
    summary: str
    status: str
    category: Optional[str]
    hours: float


@dataclass
class ProjectDetail:
    """Полный агрегат по одному проекту (правая панель)."""
    id: str
    key: str
    summary: str
    description: Optional[str]
    status: str
    status_category: Optional[str]
    category: str
    total_hours: float
    child_count: int
    employee_count: int
    period_start: Optional[datetime]
    period_end: Optional[datetime]
    weeks: Optional[float]
    rating_quality: Optional[int]
    rating_speed: Optional[int]
    rating_result: Optional[int]
    goals: Optional[str]
    planned_start_date: Optional[datetime]
    planned_end_date: Optional[datetime]
    categories: list[CategoryBreakdown] = field(default_factory=list)
    employees: list[EmployeeBreakdown] = field(default_factory=list)
    top_issues: list[TopIssue] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ProjectsService:
    """Агрегирующий сервис для страницы /projects."""

    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_projects(
        self,
        *,
        team_filter: Optional[list[str]] = None,
        status_category: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[ProjectListItem]:
        """Список проектов с метриками.

        Проект = issue с категорией quarterly_tasks или archive_target и
        без parent_id (корень иерархии).
        """
        db = self._db

        # Загружаем все «проектные» issues (корни иерархии).
        stmt = (
            select(Issue)
            .where(
                Issue.category.in_(PROJECT_CATEGORY_CODES),
                Issue.parent_id.is_(None),
            )
        )
        if status_category:
            stmt = stmt.where(Issue.status_category == status_category)
        if category:
            stmt = stmt.where(Issue.category == category)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                Issue.summary.ilike(like) | Issue.key.ilike(like)
            )

        roots: list[Issue] = db.execute(stmt).scalars().all()
        if not roots:
            return []

        root_ids = [r.id for r in roots]

        # Для каждого корня соберём все id поддерева одним обходом.
        subtree_map = self._build_subtree_map(root_ids)

        # Соберём все id задач из всех поддеревьев.
        all_issue_ids = set()
        for ids in subtree_map.values():
            all_issue_ids.update(ids)

        # Один запрос worklogs по всем задачам.
        wl_rows = (
            db.execute(
                select(
                    Worklog.issue_id,
                    Worklog.employee_id,
                    Worklog.hours,
                    Worklog.started_at,
                    Employee.team,
                )
                .join(Employee, Worklog.employee_id == Employee.id)
                .where(Worklog.issue_id.in_(all_issue_ids))
            )
            .all()
        )

        # Группируем worklogs по issue_id.
        from collections import defaultdict
        wl_by_issue: dict[str, list] = defaultdict(list)
        for row in wl_rows:
            wl_by_issue[row.issue_id].append(row)

        result: list[ProjectListItem] = []
        for root in roots:
            sub_ids = subtree_map[root.id]
            rows = [r for iid in sub_ids for r in wl_by_issue.get(iid, [])]

            # team_filter — проект включается только если есть хотя бы один
            # worklog от сотрудника из выбранных команд.
            if team_filter:
                has_team = any(r.team in team_filter for r in rows)
                if not has_team:
                    continue

            total_hours = sum(r.hours for r in rows)
            employees = {r.employee_id for r in rows}
            started_times = [r.started_at for r in rows]
            period_start = min(started_times) if started_times else None
            period_end = max(started_times) if started_times else None
            # child_count = размер поддерева минус сам корень
            child_count = len(sub_ids) - 1

            result.append(ProjectListItem(
                id=root.id,
                key=root.key,
                summary=root.summary,
                status=root.status,
                status_category=root.status_category,
                category=root.category or "",
                total_hours=total_hours,
                child_count=child_count,
                employee_count=len(employees),
                period_start=period_start,
                period_end=period_end,
                rating_quality=root.rating_quality,
                rating_speed=root.rating_speed,
                rating_result=root.rating_result,
                goals=root.goals,
                planned_start_date=root.planned_start_date,
                planned_end_date=root.planned_end_date,
            ))

        return result

    def get_project_detail(self, key: str) -> Optional[ProjectDetail]:
        """Полный агрегат по одному проекту.

        Возвращает None если issue не найден или не относится к
        PROJECT_CATEGORY_CODES.
        """
        db = self._db

        root: Optional[Issue] = (
            db.execute(
                select(Issue).where(
                    Issue.key == key,
                    Issue.category.in_(PROJECT_CATEGORY_CODES),
                    Issue.parent_id.is_(None),
                )
            )
            .scalars()
            .first()
        )
        if root is None:
            return None

        subtree_ids = self._collect_subtree(root.id)

        # Worklogs всего поддерева с join сотрудника.
        wl_rows = (
            db.execute(
                select(
                    Worklog.issue_id,
                    Worklog.employee_id,
                    Worklog.hours,
                    Worklog.started_at,
                    Employee.display_name,
                    Employee.team,
                )
                .join(Employee, Worklog.employee_id == Employee.id)
                .where(Worklog.issue_id.in_(subtree_ids))
            )
            .all()
        )

        # Часы по сотрудникам.
        from collections import defaultdict
        emp_hours: dict[str, float] = defaultdict(float)
        emp_meta: dict[str, tuple[str, Optional[str]]] = {}
        started_times: list[datetime] = []

        for row in wl_rows:
            emp_hours[row.employee_id] += row.hours
            emp_meta[row.employee_id] = (row.display_name, row.team)
            started_times.append(row.started_at)

        total_hours = sum(emp_hours.values())
        period_start = min(started_times) if started_times else None
        period_end = max(started_times) if started_times else None

        weeks: Optional[float] = None
        if period_start and period_end:
            days = (period_end - period_start).days
            weeks = round(days / 7.0, 1)

        # Часы по категориям (категория берётся с issue, а не с worklog).
        # Загружаем issues поддерева.
        sub_issues: list[Issue] = (
            db.execute(
                select(Issue).where(Issue.id.in_(subtree_ids))
            )
            .scalars()
            .all()
        )
        issue_category_map = {iss.id: iss.category for iss in sub_issues}

        cat_hours: dict[str, float] = defaultdict(float)
        for row in wl_rows:
            cat_code = issue_category_map.get(row.issue_id) or "uncategorized"
            cat_hours[cat_code] += row.hours

        # Загружаем метаданные категорий одним запросом.
        known_codes = list(cat_hours.keys())
        cat_objs: list[Category] = (
            db.execute(
                select(Category).where(Category.code.in_(known_codes))
            )
            .scalars()
            .all()
        )
        cat_meta: dict[str, tuple[str, Optional[str]]] = {
            c.code: (c.label, c.color) for c in cat_objs
        }

        categories = sorted(
            [
                CategoryBreakdown(
                    code=code,
                    label=cat_meta.get(code, ("Без категории" if code == "uncategorized" else code,))[0],
                    color=cat_meta.get(code, (None, None))[1] if code in cat_meta else None,
                    hours=hours,
                )
                for code, hours in cat_hours.items()
            ],
            key=lambda c: c.hours,
            reverse=True,
        )

        # Сотрудники, отсортированные по часам desc.
        employees = sorted(
            [
                EmployeeBreakdown(
                    employee_id=eid,
                    name=emp_meta[eid][0],
                    team=emp_meta[eid][1],
                    hours=hours,
                )
                for eid, hours in emp_hours.items()
            ],
            key=lambda e: e.hours,
            reverse=True,
        )

        # Top-5 задач по часам (только задачи с worklogs).
        issue_hours: dict[str, float] = defaultdict(float)
        for row in wl_rows:
            issue_hours[row.issue_id] += row.hours

        top_issue_ids = sorted(issue_hours, key=lambda k: issue_hours[k], reverse=True)[:5]
        top_issue_map = {iss.id: iss for iss in sub_issues}
        top_issues = [
            TopIssue(
                issue_id=iid,
                key=top_issue_map[iid].key,
                summary=top_issue_map[iid].summary,
                status=top_issue_map[iid].status,
                category=top_issue_map[iid].category,
                hours=issue_hours[iid],
            )
            for iid in top_issue_ids
            if iid in top_issue_map
        ]

        return ProjectDetail(
            id=root.id,
            key=root.key,
            summary=root.summary,
            description=root.description,
            status=root.status,
            status_category=root.status_category,
            category=root.category or "",
            total_hours=total_hours,
            child_count=len(subtree_ids) - 1,
            employee_count=len(emp_hours),
            period_start=period_start,
            period_end=period_end,
            weeks=weeks,
            rating_quality=root.rating_quality,
            rating_speed=root.rating_speed,
            rating_result=root.rating_result,
            goals=root.goals,
            planned_start_date=root.planned_start_date,
            planned_end_date=root.planned_end_date,
            categories=categories,
            employees=employees,
            top_issues=top_issues,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_subtree(self, root_id: str) -> set[str]:
        """Рекурсивный обход поддерева через parent_id.

        Возвращает set id всех issues включая корень.
        """
        visited: set[str] = set()
        queue = [root_id]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            children = self._db.execute(
                select(Issue.id).where(Issue.parent_id == current)
            ).scalars().all()
            queue.extend(children)
        return visited

    def _build_subtree_map(self, root_ids: list[str]) -> dict[str, set[str]]:
        """Строит subtree для нескольких корней.

        Загружает все issues одним запросом и раскладывает по корням.
        """
        # Загружаем все issues (id + parent_id) — достаточно для обхода.
        all_rows = self._db.execute(
            select(Issue.id, Issue.parent_id)
        ).all()

        # Строим индекс parent → children.
        from collections import defaultdict
        children_of: dict[str, list[str]] = defaultdict(list)
        for iid, pid in all_rows:
            if pid:
                children_of[pid].append(iid)

        result: dict[str, set[str]] = {}
        for root_id in root_ids:
            visited: set[str] = set()
            queue = [root_id]
            while queue:
                current = queue.pop()
                if current in visited:
                    continue
                visited.add(current)
                queue.extend(children_of[current])
            result[root_id] = visited

        return result
