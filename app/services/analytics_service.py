"""Сервис аналитики факта — агрегаты по worklog.

Отчёты:
- Часы по сотрудникам
- Часы по проектам
- Часы по категориям
- Часы по периодам (день/неделя/месяц)
- Контекстные переключения (сколько раз сотрудник переключался между проектами)
"""

import json
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import func, and_, or_, select, exists
from sqlalchemy.orm import Session

from app.models import Worklog, Issue, Employee, Project, CategoryMapping, EmployeeTeam
from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
from app.models import MandatoryWorkType, RoleCapacityRule, Category
from app.models.scenario_norm_snapshot import ScenarioNormSnapshot
from app.models.scenario_revision import ScenarioRevision
from app.api.endpoints.issue_config import ARCHIVE_CATEGORY_CODES
from app.schemas.dashboard import (
    DashboardProjectsResponse,
    ProjectAttentionItem,
    ProjectOverrunItem,
    DashboardNormWorkResponse,
    NormWorkItem,
    DashboardCategoriesResponse,
    CategoryMetaItem,
)
from app.services.categories import CATEGORY_LABELS, get_category_labels
from app.utils.period import quarter_to_dates


NO_TEAM_TOKEN = "__none__"


def parse_teams_csv(teams: Optional[str]) -> list[str]:
    """Распарсить CSV-строку команд из query-параметра в список.

    Пустая строка / None / строка только с запятыми → пустой список
    (helper должен быть no-op в таких случаях).
    """
    return [t for t in (teams.split(",") if teams else []) if t]


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

    def _apply_team_filter(
        self,
        query,
        teams: Optional[list[str]],
        match_employees: bool,
        match_issues: bool,
        issue_already_joined: bool = False,
    ):
        """Применить team-фильтр: по команде сотрудника ИЛИ по команде задачи.

        Если ``teams`` пустой или обе галочки выключены — вернуть query без изменений.
        Если нужен join ``Issue``, helper сам его добавит, когда ``issue_already_joined`` = False.
        """
        if not teams or (not match_employees and not match_issues):
            return query

        named_teams = [t for t in teams if t != NO_TEAM_TOKEN]
        has_none = NO_TEAM_TOKEN in teams

        clauses: list = []

        if match_employees:
            emp_sub_clauses: list = []
            if named_teams:
                emp_sub_clauses.append(
                    Worklog.employee_id.in_(
                        select(EmployeeTeam.employee_id).where(
                            EmployeeTeam.team.in_(named_teams)
                        )
                    )
                )
            if has_none:
                emp_sub_clauses.append(
                    ~exists().where(EmployeeTeam.employee_id == Worklog.employee_id)
                )
            if emp_sub_clauses:
                clauses.append(or_(*emp_sub_clauses) if len(emp_sub_clauses) > 1 else emp_sub_clauses[0])

        if match_issues:
            issue_sub_clauses: list = []
            if named_teams:
                named_clause = [Issue.team.in_(named_teams)]
                for t in named_teams:
                    t_json = json.dumps(t, ensure_ascii=False)  # e.g. '"Core"' or '"Team \\"Alpha\\""'
                    escaped = t_json.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    named_clause.append(
                        Issue.participating_teams.like(f"%{escaped}%", escape="\\")
                    )
                issue_sub_clauses.append(or_(*named_clause))
            if has_none:
                issue_sub_clauses.append(
                    and_(
                        Issue.team.is_(None),
                        or_(
                            Issue.participating_teams.is_(None),
                            Issue.participating_teams == "[]",
                        ),
                    )
                )
            if issue_sub_clauses:
                if not issue_already_joined:
                    query = query.join(Issue, Worklog.issue_id == Issue.id)
                clauses.append(or_(*issue_sub_clauses) if len(issue_sub_clauses) > 1 else issue_sub_clauses[0])

        if not clauses:
            return query

        final = or_(*clauses) if len(clauses) > 1 else clauses[0]
        return query.filter(final)

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
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
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
        query = self._apply_team_filter(
            query, teams, match_employees, match_issues,
            issue_already_joined=bool(project_key),
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
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
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
        query = self._apply_team_filter(
            query, teams, match_employees, match_issues,
            issue_already_joined=True,
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

    def hours_by_category(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
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
        query = self._apply_team_filter(
            query, teams, match_employees, match_issues,
            issue_already_joined=bool(project_key),
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
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
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
        query = self._apply_team_filter(
            query, teams, match_employees, match_issues,
            issue_already_joined=bool(project_key),
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

    # === Dashboard widgets ===

    def get_dashboard_projects(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        team: Optional[str] = None,
        silence_days: int = 14,
    ) -> DashboardProjectsResponse:
        """Widget 1: обзор проектов квартала из утверждённого сценария.

        Возвращает счётчики статусов, прогноз закрытия, список требующих
        внимания (просрочено или тихо) и список превышения оценки.
        """
        period_start, period_end = quarter_to_dates(year, quarter, month)
        today = date.today()

        # 1. Найти утверждённый сценарий и issue-ключи входящих задач
        approved_q = (
            self.db.query(PlanningScenario.id)
            .filter(
                PlanningScenario.year == year,
                PlanningScenario.quarter == f"Q{quarter}",
                PlanningScenario.status == "approved",
            )
        )
        if team:
            approved_q = approved_q.filter(PlanningScenario.team == team)
        scenario_ids = [row[0] for row in approved_q.all()]

        if not scenario_ids:
            return DashboardProjectsResponse(
                total=0, done=0, in_progress=0, overdue=0, not_started=0,
                forecast_done=0, forecast_pct=0.0,
                attention_list=[], overrun_list=[],
            )

        # Issue.id for all included backlog items across approved scenarios
        alloc_rows = (
            self.db.query(BacklogItem.issue_id, BacklogItem.estimate_hours)
            .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
            .filter(
                ScenarioAllocation.scenario_id.in_(scenario_ids),
                ScenarioAllocation.included_flag.is_(True),
                BacklogItem.issue_id.isnot(None),
            )
            .distinct()
            .all()
        )

        if not alloc_rows:
            return DashboardProjectsResponse(
                total=0, done=0, in_progress=0, overdue=0, not_started=0,
                forecast_done=0, forecast_pct=0.0,
                attention_list=[], overrun_list=[],
            )

        issue_ids = list({row[0] for row in alloc_rows})
        # Map issue_id → plan hours (from BacklogItem.estimate_hours)
        plan_by_issue: dict[str, float] = {}
        for issue_id, est in alloc_rows:
            if issue_id and est is not None:
                plan_by_issue[issue_id] = est

        # 2. Load Issue objects
        issues: list[Issue] = (
            self.db.query(Issue)
            .filter(Issue.id.in_(issue_ids))
            .all()
        )
        total = len(issues)

        # 3. Count by status_category
        done = sum(1 for i in issues if i.status_category == "done")
        in_progress = sum(1 for i in issues if i.status_category == "indeterminate")
        not_started = sum(1 for i in issues if i.status_category == "new")

        # 4. Overdue: not done AND due_date < today
        overdue_issues = [
            i for i in issues
            if i.status_category != "done"
            and i.due_date is not None
            and i.due_date.date() < today
        ]
        overdue = len(overdue_issues)
        overdue_ids = {i.id for i in overdue_issues}

        # 5. Forecast (linear extrapolation over the quarter)
        passed_days = (today - period_start).days
        remaining_days = (period_end - today).days
        if remaining_days <= 0:
            # Past quarter — actuals are the forecast
            forecast_done = done
            forecast_pct = round(done / total * 100, 1) if total else 0.0
        elif passed_days > 0 and done > 0:
            forecast_done = min(total, round(done / passed_days * (passed_days + remaining_days)))
            forecast_pct = round(forecast_done / total * 100, 1) if total else 0.0
        else:
            forecast_done = done
            forecast_pct = round(forecast_done / total * 100, 1) if total else 0.0

        # 6. Silence detection — last worklog date per epic
        # Worklogs on the epic itself OR on its direct children
        issue_id_set = set(issue_ids)
        silence_cutoff = datetime.utcnow() - timedelta(days=silence_days)

        # One query: max(started_at) grouped by the "root" issue id
        # For child issues: root = parent_id if parent in our set, else issue.id
        # Simpler: load max worklog date for each issue_id and its children
        child_rows = (
            self.db.query(Issue.id, Issue.parent_id)
            .filter(Issue.parent_id.in_(issue_id_set))
            .all()
        )
        child_to_parent: dict[str, str] = {r[0]: r[1] for r in child_rows}

        # IDs to query worklogs for: our epics + their children
        all_worklog_issue_ids = issue_id_set | set(child_to_parent.keys())

        wlog_rows = (
            self.db.query(Worklog.issue_id, func.max(Worklog.started_at).label("last_wl"))
            .filter(Worklog.issue_id.in_(all_worklog_issue_ids))
            .group_by(Worklog.issue_id)
            .all()
        )

        # Aggregate to root issue level
        last_activity: dict[str, datetime] = {}  # root_issue_id → last worklog datetime
        for wlog_issue_id, last_wl in wlog_rows:
            root_id = child_to_parent.get(wlog_issue_id, wlog_issue_id)
            if root_id in issue_id_set:
                existing = last_activity.get(root_id)
                if existing is None or (last_wl and last_wl > existing):
                    last_activity[root_id] = last_wl

        # 7. Fact hours per issue (worklogs on epic + children), period-scoped
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())
        fact_rows = (
            self.db.query(Worklog.issue_id, func.sum(Worklog.hours).label("hrs"))
            .filter(
                Worklog.issue_id.in_(all_worklog_issue_ids),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
            .group_by(Worklog.issue_id)
            .all()
        )
        fact_by_wlog_issue: dict[str, float] = {r[0]: float(r[1] or 0) for r in fact_rows}

        # Roll up to root
        fact_by_issue: dict[str, float] = {}
        for wlog_issue_id, hrs in fact_by_wlog_issue.items():
            root_id = child_to_parent.get(wlog_issue_id, wlog_issue_id)
            if root_id in issue_id_set:
                fact_by_issue[root_id] = fact_by_issue.get(root_id, 0.0) + hrs

        # 8. Build attention_list
        attention_list: list[ProjectAttentionItem] = []
        for issue in issues:
            if issue.status_category == "done":
                continue
            days_overdue = None
            if issue.id in overdue_ids:
                days_overdue = (today - issue.due_date.date()).days

            last_wl = last_activity.get(issue.id)
            if last_wl is None:
                days_silent = (today - period_start).days
            elif last_wl < silence_cutoff:
                days_silent = (today - last_wl.date()).days
            else:
                days_silent = None

            if days_overdue is not None or days_silent is not None:
                attention_list.append(ProjectAttentionItem(
                    issue_key=issue.key,
                    title=issue.summary,
                    fact_hours=fact_by_issue.get(issue.id, 0.0),
                    days_overdue=days_overdue,
                    days_silent=days_silent,
                ))

        # 9. Build overrun_list (only when plan_hours known)
        overrun_list: list[ProjectOverrunItem] = []
        for issue in issues:
            plan_h = plan_by_issue.get(issue.id)
            if plan_h is None:
                continue
            fact_h = fact_by_issue.get(issue.id, 0.0)
            if fact_h > plan_h:
                overrun_list.append(ProjectOverrunItem(
                    issue_key=issue.key,
                    title=issue.summary,
                    plan_hours=plan_h,
                    fact_hours=fact_h,
                    delta_hours=round(fact_h - plan_h, 2),
                ))

        return DashboardProjectsResponse(
            total=total,
            done=done,
            in_progress=in_progress,
            overdue=overdue,
            not_started=not_started,
            forecast_done=forecast_done,
            forecast_pct=forecast_pct,
            attention_list=attention_list[:10],
            overrun_list=overrun_list[:10],
        )

    # === Dashboard widgets 2 & 3 ===

    def get_dashboard_norm_work(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        teams: Optional[list[str]] = None,
    ) -> DashboardNormWorkResponse:
        """Widget 2: план/факт по обязательным видам работ за квартал/месяц.

        Для каждого активного вида работ считает:
        - plan_hours = из ScenarioNormSnapshot утверждённого сценария (последняя ревизия)
        - fact_hours = сумма ворклогов по задачам категорий, привязанных к данному виду работ
        """
        period_start, period_end = quarter_to_dates(year, quarter, month)
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())

        # 1. Все активные виды работ
        work_types: list[MandatoryWorkType] = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active.is_(True))
            .order_by(MandatoryWorkType.sort_order)
            .all()
        )

        # 2. Категории: code → work_type_id (только с привязкой)
        cat_rows = (
            self.db.query(Category.code, Category.work_type_id)
            .filter(Category.work_type_id.isnot(None))
            .all()
        )
        codes_by_work_type: dict[str, list[str]] = {}
        for code, wt_id in cat_rows:
            codes_by_work_type.setdefault(wt_id, []).append(code)

        # 3. План из утверждённого сценария квартала
        approved_scenario = (
            self.db.query(PlanningScenario)
            .filter(
                PlanningScenario.year == year,
                PlanningScenario.quarter == f"Q{quarter}",
                PlanningScenario.status == "approved",
            )
            .order_by(PlanningScenario.updated_at.desc())
            .first()
        )
        plan_by_work_type: dict[str, float] = {}
        backlog_plan_hours: float = 0.0
        if approved_scenario:
            from sqlalchemy import func as sqlfunc
            from app.services.capacity_service import QUARTER_MONTHS

            latest_revision = (
                self.db.query(ScenarioRevision)
                .filter(ScenarioRevision.scenario_id == approved_scenario.id)
                .order_by(ScenarioRevision.revision_number.desc())
                .first()
            )
            if latest_revision:
                snap_q = (
                    self.db.query(
                        ScenarioNormSnapshot.work_type_id,
                        sqlfunc.sum(ScenarioNormSnapshot.norm_hours).label("total"),
                    )
                    .filter(
                        ScenarioNormSnapshot.revision_id == latest_revision.id,
                        ScenarioNormSnapshot.year == year,
                    )
                )
                if month:
                    snap_q = snap_q.filter(ScenarioNormSnapshot.month == month)
                else:
                    snap_q = snap_q.filter(
                        ScenarioNormSnapshot.month.in_(QUARTER_MONTHS[quarter])
                    )
                if teams:
                    named_teams = [t for t in teams if t != NO_TEAM_TOKEN]
                    if named_teams:
                        emp_subq = (
                            select(EmployeeTeam.employee_id)
                            .where(EmployeeTeam.team.in_(named_teams))
                            .scalar_subquery()
                        )
                        snap_q = snap_q.filter(
                            ScenarioNormSnapshot.employee_id.in_(emp_subq)
                        )
                for wt_id, total in snap_q.group_by(ScenarioNormSnapshot.work_type_id).all():
                    if wt_id:
                        plan_by_work_type[wt_id] = round(float(total), 2)

            row = (
                self.db.query(
                    func.sum(
                        func.coalesce(BacklogItem.estimate_analyst_hours, 0.0)
                        + func.coalesce(BacklogItem.estimate_dev_hours, 0.0)
                        + func.coalesce(BacklogItem.estimate_qa_hours, 0.0)
                        + func.coalesce(BacklogItem.estimate_opo_hours, 0.0)
                    )
                )
                .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
                .filter(
                    ScenarioAllocation.scenario_id == approved_scenario.id,
                    ScenarioAllocation.included_flag == True,  # noqa: E712
                )
                .scalar()
            )
            backlog_plan_hours = float(row or 0.0)

        # 5. Факт по видам работ — один групповой запрос вместо N запросов
        all_category_codes = [code for codes in codes_by_work_type.values() for code in codes]
        fact_by_code: dict[str, float] = {}
        if all_category_codes:
            fact_q = (
                self.db.query(Issue.category, func.sum(Worklog.hours))
                .join(Worklog, Worklog.issue_id == Issue.id)
                .filter(
                    Worklog.started_at >= start_dt,
                    Worklog.started_at <= end_dt,
                    Issue.category.in_(all_category_codes),
                )
            )
            if teams:
                named_teams = [t for t in teams if t != NO_TEAM_TOKEN]
                has_none = NO_TEAM_TOKEN in teams
                emp_clauses: list = []
                if named_teams:
                    emp_subq = select(EmployeeTeam.employee_id).where(
                        EmployeeTeam.team.in_(named_teams)
                    ).scalar_subquery()
                    emp_clauses.append(Worklog.employee_id.in_(emp_subq))
                if has_none:
                    emp_clauses.append(
                        ~exists().where(EmployeeTeam.employee_id == Worklog.employee_id)
                    )
                if emp_clauses:
                    fact_q = fact_q.filter(
                        or_(*emp_clauses) if len(emp_clauses) > 1 else emp_clauses[0]
                    )
            rows = fact_q.group_by(Issue.category).all()
            fact_by_code = {code: float(hours or 0) for code, hours in rows}

        items: list[NormWorkItem] = []
        for wt in work_types:
            fact_hours = sum(fact_by_code.get(code, 0.0) for code in codes_by_work_type.get(wt.id, []))

            if wt.id in plan_by_work_type:
                plan_hours = round(plan_by_work_type[wt.id], 2)
            elif fact_hours > 0 and backlog_plan_hours > 0:
                # нет правила в сценарии, но есть факт → проектная работа
                plan_hours = round(backlog_plan_hours, 2)
            else:
                plan_hours = 0.0
            pct_actual = round(fact_hours / plan_hours * 100, 1) if plan_hours > 0 else 0.0

            items.append(NormWorkItem(
                work_type_id=wt.id,
                label=wt.label,
                plan_hours=plan_hours,
                fact_hours=round(fact_hours, 2),
                pct=pct_actual,
            ))

        items = [i for i in items if i.plan_hours > 0 or i.fact_hours > 0]
        total_plan = round(sum(i.plan_hours for i in items), 2)
        total_fact = round(sum(i.fact_hours for i in items), 2)
        total_pct = round(total_fact / total_plan * 100, 1) if total_plan > 0 else 0.0

        return DashboardNormWorkResponse(
            items=items,
            total_plan=total_plan,
            total_fact=total_fact,
            total_pct=total_pct,
        )

    def get_dashboard_categories(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        teams: Optional[list[str]] = None,
    ) -> DashboardCategoriesResponse:
        """Widget 3: метрики по категориям работ за квартал/месяц.

        Исключает архивные категории. Считает часы, число ворклогов,
        задач и сотрудников, среднюю длительность ворклога.
        """
        _DEFAULT_COLOR = "#8884d8"

        period_start, period_end = quarter_to_dates(year, quarter, month)
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())

        # 1. Активные не-архивные категории: code → (label, color)
        cat_rows = (
            self.db.query(Category.code, Category.label, Category.color)
            .filter(Category.code.not_in(ARCHIVE_CATEGORY_CODES))
            .all()
        )
        cat_meta: dict[str, tuple[str, str]] = {
            row.code: (row.label, row.color or _DEFAULT_COLOR)
            for row in cat_rows
        }
        allowed_codes = list(cat_meta.keys())

        # 2. Агрегат по категории задачи
        agg_q = (
            self.db.query(
                Issue.category.label("category"),
                func.sum(Worklog.hours).label("hours"),
                func.count(Worklog.id).label("worklog_count"),
                func.count(func.distinct(Issue.id)).label("issue_count"),
                func.count(func.distinct(Worklog.employee_id)).label("employee_count"),
                func.avg(Worklog.hours * 60).label("avg_worklog_minutes"),
            )
            .join(Issue, Worklog.issue_id == Issue.id)
            .filter(
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
                Issue.category.in_(allowed_codes),
            )
        )
        if teams:
            named_teams = [t for t in teams if t != NO_TEAM_TOKEN]
            has_none = NO_TEAM_TOKEN in teams
            emp_clauses: list = []
            if named_teams:
                emp_subq = select(EmployeeTeam.employee_id).where(
                    EmployeeTeam.team.in_(named_teams)
                ).scalar_subquery()
                emp_clauses.append(Worklog.employee_id.in_(emp_subq))
            if has_none:
                emp_clauses.append(
                    ~exists().where(EmployeeTeam.employee_id == Worklog.employee_id)
                )
            if emp_clauses:
                agg_q = agg_q.filter(
                    or_(*emp_clauses) if len(emp_clauses) > 1 else emp_clauses[0]
                )
        agg_rows = agg_q.group_by(Issue.category).all()

        items: list[CategoryMetaItem] = []
        for row in agg_rows:
            label, color = cat_meta.get(row.category, (row.category, _DEFAULT_COLOR))
            items.append(CategoryMetaItem(
                key=row.category,
                label=label,
                color=color,
                hours=round(float(row.hours or 0), 2),
                worklog_count=int(row.worklog_count or 0),
                issue_count=int(row.issue_count or 0),
                employee_count=int(row.employee_count or 0),
                avg_worklog_minutes=round(float(row.avg_worklog_minutes or 0), 1),
                pct=0.0,  # computed below
            ))

        items.sort(key=lambda x: x.hours, reverse=True)
        total_hours = round(sum(i.hours for i in items), 2)

        for item in items:
            item.pct = round(item.hours / total_hours * 100, 1) if total_hours > 0 else 0.0

        return DashboardCategoriesResponse(items=items, total_hours=total_hours)

    # === Контекстные переключения ===

    def context_switching(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        employee_id: Optional[str] = None,
        project_key: Optional[str] = None,
        teams: Optional[list[str]] = None,
        match_employees: bool = True,
        match_issues: bool = True,
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
        query = self._apply_team_filter(
            query, teams, match_employees, match_issues,
            issue_already_joined=True,
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
