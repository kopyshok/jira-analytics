"""Сервис аналитики факта — агрегаты по worklog.

Отчёты:
- Часы по сотрудникам
- Часы по проектам
- Часы по категориям
- Часы по периодам (день/неделя/месяц)
- Контекстные переключения (сколько раз сотрудник переключался между проектами)
"""

import json
from datetime import datetime, date, timedelta
from typing import Optional

from sqlalchemy import func, and_, or_, select, exists
from sqlalchemy.orm import Session, joinedload

from app.models import Worklog, Issue, Employee, EmployeeTeam
from app.models import BacklogItem, PlanningScenario, ScenarioAllocation
from app.models import MandatoryWorkType, RoleCapacityRule, Category, Role
from app.models.absence import Absence
from app.models.absence_reason import AbsenceReason
from app.api.endpoints.issue_config import ARCHIVE_CATEGORY_CODES
from app.schemas.dashboard import (
    DashboardProjectsResponse,
    DashboardNormWorkResponse,
    DashboardCategoriesResponse,
    CategoryMetaItem,
    EmployeeWorklogActivity,
)
from app.utils.period import quarter_to_dates


NO_TEAM_TOKEN = "__none__"


def _initials(name: str) -> str:
    """Инициалы сотрудника из полного имени (2 буквы)."""
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "??"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _empty_totals() -> "NodeTotals":
    """Пустые итоги для узлов без данных."""
    from app.schemas.analytics_report import NodeTotals
    return NodeTotals(
        fact_hours=0.0, plan_hours=None, pct_plan=None, pct_total=0.0,
        pct_in_group=None,
        worklog_count=0, issue_count=0, employee_count=0, avg_worklog_minutes=0.0,
        foreign_issue_count=0, foreign_hours=0.0, foreign_pct=0.0,
    )


def _classify_foreign(
    emp_team: str | None,
    issue_team: str | None,
    parts_json: str | None,
) -> bool:
    """True если ворклог на чужую задачу (issue не принадлежит команде сотрудника)."""
    if not emp_team:
        return False  # Сотрудник без primary-команды — fallback на старое поведение
    parts: list[str] = []
    if parts_json:
        try:
            decoded = json.loads(parts_json)
            if isinstance(decoded, list):
                parts = [p for p in decoded if isinstance(p, str)]
        except ValueError:
            pass
    if not issue_team:
        return True
    if issue_team == emp_team or emp_team in parts:
        return False
    return True


def parse_teams_csv(teams: Optional[str]) -> list[str]:
    """Распарсить CSV-строку команд из query-параметра в список.

    Пустая строка / None / строка только с запятыми → пустой список
    (helper должен быть no-op в таких случаях).
    """
    return [t for t in (teams.split(",") if teams else []) if t]


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


    def get_dashboard_projects(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        teams: Optional[list[str]] = None,
        silence_days: int = 14,
    ) -> DashboardProjectsResponse:
        """Widget 1: обзор проектов квартала из утверждённого сценария."""
        from app.schemas.dashboard import ProjectItem, ProjectAssignee

        period_start, period_end = quarter_to_dates(year, quarter, month)
        today = date.today()
        today_dt = datetime.combine(today, datetime.min.time())

        # 1. Утверждённый сценарий
        approved_q = (
            self.db.query(PlanningScenario.id)
            .filter(
                PlanningScenario.year == year,
                PlanningScenario.quarter == f"Q{quarter}",
                PlanningScenario.status == "approved",
            )
        )
        if teams:
            approved_q = approved_q.filter(PlanningScenario.team.in_(teams))
        scenario_ids = [row[0] for row in approved_q.all()]

        empty_response = DashboardProjectsResponse(
            total=0, done=0, in_progress=0, overdue=0, not_started=0,
            total_fact_hours=0.0, total_plan_hours=0.0, avg_load_pct=0.0,
            silent_count=0, forecast_done=0, forecast_pct=0.0,
            projects=[],
        )

        if not scenario_ids:
            return empty_response

        from app.services.allocation_estimates import effective_estimate_hours

        alloc_objs = (
            self.db.query(ScenarioAllocation)
            .options(joinedload(ScenarioAllocation.backlog_item))
            .filter(
                ScenarioAllocation.scenario_id.in_(scenario_ids),
                ScenarioAllocation.included_flag.is_(True),
            )
            .all()
        )
        # Несколько allocations на один issue (разные approved сценарии) —
        # берём максимум как «целевой план» по этой инициативе. Override на
        # allocation приоритетнее BacklogItem.estimate_*.
        plan_by_issue: dict[str, float] = {}
        for a in alloc_objs:
            bi = a.backlog_item
            if bi is None or bi.issue_id is None:
                continue
            eff = effective_estimate_hours(a)
            total = eff["analyst"] + eff["dev"] + eff["qa"] + eff["opo"]
            prev = plan_by_issue.get(bi.issue_id, 0.0)
            if total > prev:
                plan_by_issue[bi.issue_id] = total

        if not plan_by_issue:
            return empty_response

        issue_ids = list(plan_by_issue.keys())

        issues: list[Issue] = self.db.query(Issue).filter(Issue.id.in_(issue_ids)).all()
        total = len(issues)

        # Статусы
        done = sum(1 for i in issues if i.status_category == "done")
        in_progress = sum(1 for i in issues if i.status_category == "indeterminate")
        not_started = sum(1 for i in issues if i.status_category == "new")
        overdue_issues = [
            i for i in issues
            if i.status_category != "done"
            and i.due_date is not None
            and i.due_date.date() < today
        ]
        overdue = len(overdue_issues)

        # Дети эпиков (для агрегаций)
        issue_id_set = set(issue_ids)
        children = (
            self.db.query(Issue.id, Issue.parent_id, Issue.status_category)
            .filter(Issue.parent_id.in_(issue_id_set))
            .all()
        )
        child_to_parent: dict[str, str] = {r[0]: r[1] for r in children}
        subtasks_done_by_parent: dict[str, int] = {}
        subtasks_total_by_parent: dict[str, int] = {}
        for child_id, parent_id, child_status in children:
            subtasks_total_by_parent[parent_id] = subtasks_total_by_parent.get(parent_id, 0) + 1
            if child_status == "done":
                subtasks_done_by_parent[parent_id] = subtasks_done_by_parent.get(parent_id, 0) + 1

        # Все ID для ворклог-агрегаций
        all_wl_ids = issue_id_set | set(child_to_parent.keys())

        # Last worklog per epic (для silence)
        last_wl_rows = (
            self.db.query(Worklog.issue_id, func.max(Worklog.started_at).label("last_wl"))
            .filter(Worklog.issue_id.in_(all_wl_ids))
            .group_by(Worklog.issue_id)
            .all()
        )
        last_wl_by_issue: dict[str, datetime] = {r[0]: r[1] for r in last_wl_rows if r[1] is not None}

        def epic_last_wl(epic_id: str) -> datetime | None:
            candidates = [last_wl_by_issue.get(epic_id)]
            for child_id, parent_id in child_to_parent.items():
                if parent_id == epic_id and child_id in last_wl_by_issue:
                    candidates.append(last_wl_by_issue[child_id])
            candidates = [c for c in candidates if c is not None]
            return max(candidates) if candidates else None

        # Суммарный факт по эпику (включая детей) в пределах периода
        period_start_dt = datetime.combine(period_start, datetime.min.time())
        period_end_dt = datetime.combine(period_end, datetime.max.time())
        fact_rows = (
            self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
            .filter(
                Worklog.issue_id.in_(all_wl_ids),
                Worklog.started_at >= period_start_dt,
                Worklog.started_at <= period_end_dt,
            )
            .group_by(Worklog.issue_id)
            .all()
        )
        fact_secs_by_issue: dict[str, int] = {r[0]: r[1] or 0 for r in fact_rows}

        def epic_fact_hours(epic_id: str) -> float:
            secs = fact_secs_by_issue.get(epic_id, 0)
            for child_id, parent_id in child_to_parent.items():
                if parent_id == epic_id:
                    secs += fact_secs_by_issue.get(child_id, 0)
            return secs / 3600.0

        # Тренд: часы за последние 7д vs предыдущие 7д
        trend_cutoff_now = today_dt - timedelta(days=7)
        trend_cutoff_prev = today_dt - timedelta(days=14)

        last7_rows = (
            self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
            .filter(Worklog.issue_id.in_(all_wl_ids), Worklog.started_at >= trend_cutoff_now)
            .group_by(Worklog.issue_id)
            .all()
        )
        last7_secs: dict[str, int] = {r[0]: r[1] or 0 for r in last7_rows}

        prev7_rows = (
            self.db.query(Worklog.issue_id, func.sum(Worklog.time_spent_seconds).label("secs"))
            .filter(
                Worklog.issue_id.in_(all_wl_ids),
                Worklog.started_at >= trend_cutoff_prev,
                Worklog.started_at < trend_cutoff_now,
            )
            .group_by(Worklog.issue_id)
            .all()
        )
        prev7_secs: dict[str, int] = {r[0]: r[1] or 0 for r in prev7_rows}

        def epic_trend(epic_id: str) -> tuple[float, str]:
            last_secs = last7_secs.get(epic_id, 0)
            prev_secs = prev7_secs.get(epic_id, 0)
            for child_id, parent_id in child_to_parent.items():
                if parent_id == epic_id:
                    last_secs += last7_secs.get(child_id, 0)
                    prev_secs += prev7_secs.get(child_id, 0)
            last_h = last_secs / 3600.0
            if last_h < 0.5 and prev_secs / 3600.0 < 0.5:
                return (0.0, "flat")
            if last_secs > prev_secs * 1.1:
                return (round(last_h, 1), "up")
            if last_secs < prev_secs * 0.9:
                return (round(last_h, 1), "down")
            return (round(last_h, 1), "flat")

        # Assignees: top-3 по часам в эпике
        asg_rows = (
            self.db.query(
                Worklog.issue_id,
                Worklog.employee_id,
                func.sum(Worklog.time_spent_seconds).label("secs"),
            )
            .filter(Worklog.issue_id.in_(all_wl_ids))
            .group_by(Worklog.issue_id, Worklog.employee_id)
            .all()
        )
        epic_to_employees: dict[str, dict[str, int]] = {}
        for issue_id, employee_id, secs in asg_rows:
            epic_id = child_to_parent.get(issue_id, issue_id) if issue_id in child_to_parent else issue_id
            d = epic_to_employees.setdefault(epic_id, {})
            d[employee_id] = d.get(employee_id, 0) + (secs or 0)

        employee_ids = {eid for d in epic_to_employees.values() for eid in d.keys()}
        employees = self.db.query(Employee).filter(Employee.id.in_(employee_ids)).all() if employee_ids else []
        emp_by_id: dict[str, Employee] = {e.id: e for e in employees}

        def employee_initials(name: str) -> str:
            parts = [p for p in name.split() if p]
            if not parts:
                return "??"
            if len(parts) == 1:
                return parts[0][:2].upper()
            return (parts[0][0] + parts[1][0]).upper()

        # Pre-load Role.color by code for assignee avatars
        all_roles = self.db.query(Role).all()
        role_color_by_code: dict[str, str] = {r.code: r.color for r in all_roles if r.color}

        def employee_color(emp: "Employee | None") -> str:
            if emp and emp.role and emp.role in role_color_by_code:
                return role_color_by_code[emp.role]
            return "#7e94b8"

        # Forecast close date per epic
        quarter_end = period_end

        first_wl_rows = (
            self.db.query(Worklog.issue_id, func.min(Worklog.started_at).label("first_wl"))
            .filter(Worklog.issue_id.in_(all_wl_ids))
            .group_by(Worklog.issue_id)
            .all()
        )
        first_wl_by_issue: dict[str, datetime] = {r[0]: r[1] for r in first_wl_rows if r[1] is not None}

        def epic_forecast(epic_id: str, plan_h: float, fact_h: float) -> tuple[date | None, bool]:
            if fact_h <= 0:
                return (None, False)
            last_wl = epic_last_wl(epic_id)
            relevant_ids = {epic_id} | {cid for cid, pid in child_to_parent.items() if pid == epic_id}
            candidates = [first_wl_by_issue[i] for i in relevant_ids if i in first_wl_by_issue]
            if not candidates:
                return (None, False)
            first_dt = min(candidates)
            days_active = max(1, (today_dt - first_dt).days)
            rate_per_day = fact_h / days_active
            if rate_per_day <= 0:
                return (None, False)
            if fact_h >= plan_h:
                close = last_wl.date() if last_wl else today
                return (close, close <= quarter_end)
            remaining_h = plan_h - fact_h
            days_to_close = remaining_h / rate_per_day
            close_date = today + timedelta(days=int(days_to_close))
            return (close_date, close_date <= quarter_end)

        # Weekly activity (8 точек) — по неделям периода с конца назад
        week_buckets = []
        cursor = period_end_dt
        for _ in range(8):
            wk_start = cursor - timedelta(days=7)
            week_buckets.append((wk_start, cursor))
            cursor = wk_start
        week_buckets.reverse()

        weekly_activity_per_epic: dict[str, list[float]] = {epic_id: [0.0] * 8 for epic_id in issue_ids}

        window_start = week_buckets[0][0]
        window_rows = (
            self.db.query(Worklog.issue_id, Worklog.started_at, Worklog.time_spent_seconds)
            .filter(
                Worklog.issue_id.in_(all_wl_ids),
                Worklog.started_at >= window_start,
                Worklog.started_at < period_end_dt,
            )
            .all()
        )

        for issue_id, started_at, secs in window_rows:
            epic_id = child_to_parent.get(issue_id, issue_id) if issue_id in child_to_parent else issue_id
            if epic_id not in weekly_activity_per_epic:
                continue
            for idx, (wk_start, wk_end) in enumerate(week_buckets):
                if wk_start <= started_at < wk_end:
                    weekly_activity_per_epic[epic_id][idx] += (secs or 0) / 3600.0
                    break

        # KPI top-level
        overdue_ids = {i.id for i in overdue_issues}

        project_items: list[ProjectItem] = []
        total_fact = 0.0
        total_plan = 0.0
        silent_count = 0

        for issue in issues:
            plan_h = plan_by_issue.get(issue.id, 0.0) or 0.0
            fact_h = epic_fact_hours(issue.id)
            total_fact += fact_h
            total_plan += plan_h

            last_wl = epic_last_wl(issue.id)
            silent_d = (today_dt - last_wl).days if last_wl else 9999
            if silent_d > silence_days and issue.status_category != "done":
                silent_count += 1

            trend_h, trend_dir = epic_trend(issue.id)
            forecast_close, in_qtr = epic_forecast(issue.id, plan_h, fact_h)

            ui_status = issue.status_category
            if issue.id in overdue_ids:
                ui_status = "overdue"

            emp_secs = epic_to_employees.get(issue.id, {})
            sorted_emps = sorted(emp_secs.items(), key=lambda x: -x[1])
            top3 = sorted_emps[:3]
            assignees = []
            for emp_id, _ in top3:
                emp = emp_by_id.get(emp_id)
                if emp:
                    assignees.append(ProjectAssignee(
                        initials=employee_initials(emp.display_name or ""),
                        color=employee_color(emp),
                    ))
            assignees_total = len(emp_secs)

            days_to_due_val: int | None = None
            if issue.due_date is not None:
                days_to_due_val = (issue.due_date.date() - today).days

            project_items.append(ProjectItem(
                issue_key=issue.key,
                title=issue.summary or "",
                status=issue.status or "",
                status_category=ui_status,
                plan_hours=round(plan_h, 1),
                fact_hours=round(fact_h, 1),
                delta_hours=round(fact_h - plan_h, 1),
                subtasks_done=subtasks_done_by_parent.get(issue.id, 0),
                subtasks_total=subtasks_total_by_parent.get(issue.id, 0),
                assignees=assignees,
                assignees_total=assignees_total,
                due_date=issue.due_date.date() if issue.due_date else None,
                days_to_due=days_to_due_val,
                trend_hours_week=trend_h,
                trend_dir=trend_dir,
                forecast_close_date=forecast_close,
                forecast_in_quarter=in_qtr,
                silent_days=min(silent_d, 9999),
                weekly_activity=[round(h, 1) for h in weekly_activity_per_epic.get(issue.id, [0.0] * 8)],
            ))

        status_order = {"overdue": 0, "indeterminate": 1, "new": 2, "done": 3}
        project_items.sort(key=lambda p: (status_order.get(p.status_category, 99), -p.fact_hours))

        avg_load = (total_fact / total_plan * 100) if total_plan > 0 else 0.0

        passed_days = (today - period_start).days
        remaining_days = (period_end - today).days
        if remaining_days <= 0:
            forecast_done = done
            forecast_pct = round(done / total * 100, 1) if total else 0.0
        elif passed_days > 0 and done > 0:
            forecast_done = min(total, round(done / passed_days * (passed_days + remaining_days)))
            forecast_pct = round(forecast_done / total * 100, 1) if total else 0.0
        else:
            forecast_done = done
            forecast_pct = round(forecast_done / total * 100, 1) if total else 0.0

        return DashboardProjectsResponse(
            total=total,
            done=done,
            in_progress=in_progress,
            overdue=overdue,
            not_started=not_started,
            total_fact_hours=round(total_fact, 1),
            total_plan_hours=round(total_plan, 1),
            avg_load_pct=round(avg_load, 1),
            silent_count=silent_count,
            forecast_done=forecast_done,
            forecast_pct=forecast_pct,
            projects=project_items,
        )

    # === Dashboard widgets 2 & 3 ===

    def _build_plan_per_emp_wt(
        self,
        year: int,
        quarter: int,
        month: Optional[int],
        teams: Optional[list[str]],
        employees: list["Employee"],
        work_types: list["MandatoryWorkType"],
    ) -> dict[str, dict[str, float]]:
        """Plan hours per employee × work_type.

        Приоритет правил: ScenarioRule утверждённого сценария →
        RoleCapacityRule (глобальный шаблон). Возвращает словарь
        ``{employee_id: {work_type_id: hours}}``.
        """
        from app.services.capacity_service import CapacityService
        from app.models.employee_capacity_override import EmployeeCapacityOverride
        from app.models.scenario_rule import ScenarioRule

        # 1. Rules: approved scenario → template
        rules_by_role: dict[str | None, dict[str, float]] = {}

        approved_q = (
            self.db.query(PlanningScenario.id)
            .filter(
                PlanningScenario.year == year,
                PlanningScenario.quarter == f"Q{quarter}",
                PlanningScenario.status == "approved",
            )
        )
        if teams:
            approved_q = approved_q.filter(PlanningScenario.team.in_(teams))
        approved_ids = [r[0] for r in approved_q.all()]

        if approved_ids:
            for sr in self.db.query(ScenarioRule).filter(
                ScenarioRule.scenario_id.in_(approved_ids)
            ).all():
                rules_by_role.setdefault(sr.role, {})[sr.work_type_id] = sr.percent_of_norm

        if not rules_by_role:
            for rule in self.db.query(RoleCapacityRule).filter(
                RoleCapacityRule.year == year, RoleCapacityRule.quarter == quarter,
            ).all():
                rules_by_role.setdefault(rule.role, {})[rule.work_type_id] = rule.percent_of_norm

        # 2. Per-employee overrides
        overrides_by_emp: dict[str, dict[str, float]] = {}
        for ov in self.db.query(EmployeeCapacityOverride).filter(
            EmployeeCapacityOverride.year == year,
            EmployeeCapacityOverride.quarter == quarter,
        ).all():
            overrides_by_emp.setdefault(ov.employee_id, {})[ov.work_type_id] = ov.percent_of_norm

        def pct_for(emp_role: str | None, emp_id: str, wt_id: str) -> float:
            ov = overrides_by_emp.get(emp_id, {})
            if wt_id in ov:
                return ov[wt_id]
            r = rules_by_role.get(emp_role, {})
            if wt_id in r:
                return r[wt_id]
            return rules_by_role.get(None, {}).get(wt_id, 0.0)

        # 3. Base hours via CapacityService (fallback: 8h × weekdays when no calendar rows)
        cap_svc = CapacityService(self.db)
        base_hours_by_emp: dict[str, float] = {}
        try:
            team_caps = cap_svc.team_quarter_capacity(
                year=year, quarter=quarter,
                employee_ids=[e.id for e in employees],
            )
        except ValueError:
            team_caps = []
        for qcap in team_caps:
            if month is not None:
                mcap = next((m for m in qcap.months if m.month == month), None)
                base_hours_by_emp[qcap.employee_id] = mcap.available_hours if mcap else 0.0
            else:
                base_hours_by_emp[qcap.employee_id] = qcap.total_available_hours
        for emp in employees:
            base_hours_by_emp.setdefault(emp.id, 0.0)

        # 4. Assemble plan per emp × wt; project_wt gets the remainder
        project_wt = next((wt for wt in work_types if wt.code == "project"), None)
        plan_per_emp_wt: dict[str, dict[str, float]] = {}
        for emp in employees:
            base = base_hours_by_emp.get(emp.id, 0.0)
            per_wt: dict[str, float] = {}
            mandatory_total = 0.0
            for wt in work_types:
                if project_wt is not None and wt.id == project_wt.id:
                    continue
                p = pct_for(emp.role, emp.id, wt.id)
                if p > 0:
                    h = base * p / 100.0
                    per_wt[wt.id] = h
                    mandatory_total += h
            if project_wt is not None:
                per_wt[project_wt.id] = max(0.0, base - mandatory_total)
            plan_per_emp_wt[emp.id] = per_wt

        return plan_per_emp_wt

    def get_dashboard_norm_work(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        teams: Optional[list[str]] = None,
    ) -> DashboardNormWorkResponse:
        """Widget 2: per-employee план/факт по обязательным видам работ, группировка по ролям."""
        from app.schemas.dashboard import (
            NormWorkTypeBreakdown, NormWorkEmployee, NormWorkRoleGroup,
        )
        from app.models.employee_team import EmployeeTeam

        period_start, period_end = quarter_to_dates(year, quarter, month)
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())

        # 1. Активные виды работ
        work_types: list[MandatoryWorkType] = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active.is_(True))
            .order_by(MandatoryWorkType.sort_order)
            .all()
        )
        other_foreign_wt = next(
            (wt for wt in work_types if wt.code == "other_foreign"), None
        )

        # 2. Категории → work_type
        cat_rows = (
            self.db.query(Category.code, Category.work_type_id)
            .filter(Category.work_type_id.isnot(None))
            .all()
        )
        code_to_wt: dict[str, str] = {code: wt_id for code, wt_id in cat_rows}

        # 3. Активные сотрудники в командах
        employees_q = self.db.query(Employee).filter(Employee.is_active.is_(True))
        if teams:
            team_emp_ids = (
                self.db.query(EmployeeTeam.employee_id)
                .filter(EmployeeTeam.team.in_(teams))
                .distinct()
                .all()
            )
            emp_ids = [r[0] for r in team_emp_ids]
            employees_q = employees_q.filter(Employee.id.in_(emp_ids))
        employees: list[Employee] = employees_q.all()

        if not employees:
            return DashboardNormWorkResponse(
                roles=[], total_plan=0.0, total_fact=0.0, total_pct=0.0,
            )

        # Team каждого сотрудника для классификации «чужой» задачи. Совпадает
        # с логикой иерархического отчёта Аналитики: если активен фильтр teams,
        # выбираем primary (если он в фильтре) либо первое совпавшее членство;
        # без фильтра — primary.
        emp_team_rows = (
            self.db.query(EmployeeTeam.employee_id, EmployeeTeam.team, EmployeeTeam.is_primary)
            .filter(EmployeeTeam.employee_id.in_([e.id for e in employees]))
            .all()
        )
        emp_teams_all: dict[str, list[str]] = {}
        emp_primary: dict[str, str] = {}
        for row in emp_team_rows:
            emp_teams_all.setdefault(row.employee_id, []).append(row.team)
            if row.is_primary:
                emp_primary[row.employee_id] = row.team

        emp_team_by_id: dict[str, str] = {}
        if teams:
            team_set = set(teams)
            for e in employees:
                primary = emp_primary.get(e.id)
                if primary and primary in team_set:
                    emp_team_by_id[e.id] = primary
                    continue
                for t in emp_teams_all.get(e.id, []):
                    if t in team_set:
                        emp_team_by_id[e.id] = t
                        break
        else:
            emp_team_by_id = dict(emp_primary)

        # 4. Роли реестр
        roles_db: list[Role] = self.db.query(Role).filter(Role.is_active.is_(True)).order_by(Role.sort_order).all()
        role_by_code: dict[str, Role] = {r.code: r for r in roles_db}

        # 5. Plan per emp × work_type (approved scenario → template rules → capacity fallback)
        plan_per_emp_wt = self._build_plan_per_emp_wt(
            year=year, quarter=quarter, month=month,
            teams=teams, employees=employees, work_types=work_types,
        )

        # «Проектные работы» — особый work_type code='project':
        #   план = base − Σ(план остальных work_types)
        #   факт = ворклоги в задачах из утверждённых элементов бэклога + всё их поддерево
        project_wt = next((wt for wt in work_types if wt.code == "project"), None)

        # approved_scenario_ids needed for project fact below — re-query after plan helper
        approved_scenario_q = (
            self.db.query(PlanningScenario.id)
            .filter(
                PlanningScenario.year == year,
                PlanningScenario.quarter == f"Q{quarter}",
                PlanningScenario.status == "approved",
            )
        )
        if teams:
            approved_scenario_q = approved_scenario_q.filter(
                PlanningScenario.team.in_(teams)
            )
        approved_scenario_ids = [r[0] for r in approved_scenario_q.all()]

        # 6. Факт per emp × work_type из ворклогов (worklog → issue.category → category.work_type_id).
        # Используем denormalized Issue.category (учитывает наследование от родителя
        # и scope_root через CategoryResolver/MappingService), а не Issue.assigned_category —
        # иначе теряем часы на дочерних задачах без собственной ручной метки.
        #
        # Cross-team routing: если задача принадлежит чужой продуктовой команде
        # (issue.team не совпадает с primary-командой сотрудника и сотрудник не
        # числится в participating_teams), факт идёт в work_type 'other_foreign'
        # независимо от категории задачи. Пустая team задачи = чужая.
        emp_ids_list = [e.id for e in employees]
        wl_rows = (
            self.db.query(
                Worklog.employee_id,
                Issue.category,
                Issue.assigned_category,
                Issue.team,
                Issue.participating_teams,
                func.sum(Worklog.time_spent_seconds).label("secs"),
            )
            .join(Issue, Issue.id == Worklog.issue_id)
            .filter(
                Worklog.employee_id.in_(emp_ids_list),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
                Issue.include_in_analysis != False,  # noqa: E712
            )
            .group_by(
                Worklog.employee_id,
                Issue.category,
                Issue.assigned_category,
                Issue.team,
                Issue.participating_teams,
            )
            .all()
        )
        # Orphan-bucket: ворклоги без категории или с категорией без work_type_id
        # учитываются в виртуальной строке «Не указана категория/вид работ».
        ORPHAN_WT_ID = "__unmapped__"
        ORPHAN_WT_LABEL = "Не указана категория/вид работ"

        fact_per_emp_wt: dict[str, dict[str, float]] = {e.id: {} for e in employees}
        # Справочный счётчик чужих часов: суммируется по всем foreign-ворклогам
        # независимо от того, ушли ли часы в other_foreign WT или в обычную
        # категорию через assigned_category. Совпадает с классификацией в
        # иерархическом отчёте Аналитики (`_classify_foreign`).
        foreign_fact_per_emp: dict[str, float] = {e.id: 0.0 for e in employees}
        for emp_id, cat_code, assigned_cat, issue_team, parts_json, secs in wl_rows:
            h = (secs or 0) / 3600.0
            emp_team = emp_team_by_id.get(emp_id)

            is_foreign = _classify_foreign(emp_team, issue_team, parts_json)
            if is_foreign:
                foreign_fact_per_emp[emp_id] = foreign_fact_per_emp.get(emp_id, 0.0) + h

            # Чужая задача без ручной assigned_category → other_foreign.
            # Если категория проставлена руками — она перебивает foreign-routing,
            # факт идёт в work_type категории как у нормальной задачи.
            if is_foreign and other_foreign_wt is not None and not assigned_cat:
                fact_per_emp_wt[emp_id][other_foreign_wt.id] = (
                    fact_per_emp_wt[emp_id].get(other_foreign_wt.id, 0.0) + h
                )
                continue

            # Стандартный routing — по категории задачи.
            # cat_code is None → orphan; cat_code без mapping → orphan.
            if cat_code is None:
                fact_per_emp_wt[emp_id][ORPHAN_WT_ID] = (
                    fact_per_emp_wt[emp_id].get(ORPHAN_WT_ID, 0.0) + h
                )
                continue
            wt_id = code_to_wt.get(cat_code)
            if wt_id is None:
                fact_per_emp_wt[emp_id][ORPHAN_WT_ID] = (
                    fact_per_emp_wt[emp_id].get(ORPHAN_WT_ID, 0.0) + h
                )
                continue
            # Факт по project считаем отдельно (через scenario allocations) — пропускаем здесь.
            if project_wt is not None and wt_id == project_wt.id:
                continue
            fact_per_emp_wt[emp_id][wt_id] = fact_per_emp_wt[emp_id].get(wt_id, 0.0) + h

        # 8b. Факт по проектным работам — ворклоги в задачах утверждённых элементов
        # бэклога + всё их поддерево (родитель + все потомки).
        if project_wt is not None and approved_scenario_ids:
            from app.models.backlog_item import BacklogItem
            from app.models.scenario_allocation import ScenarioAllocation

            root_rows = (
                self.db.query(BacklogItem.issue_id)
                .join(ScenarioAllocation, ScenarioAllocation.backlog_item_id == BacklogItem.id)
                .filter(
                    ScenarioAllocation.scenario_id.in_(approved_scenario_ids),
                    ScenarioAllocation.included_flag.is_(True),
                    BacklogItem.issue_id.isnot(None),
                )
                .distinct()
                .all()
            )
            project_issue_ids: set[str] = {r[0] for r in root_rows if r[0]}

            # BFS вниз по parent_id: разворачиваем поддерево. Чанкуем по 500 ради SQLite
            # (limit 999 переменных в IN).
            CHUNK = 500
            frontier = list(project_issue_ids)
            while frontier:
                new_ids: set[str] = set()
                for i in range(0, len(frontier), CHUNK):
                    chunk = frontier[i : i + CHUNK]
                    children = (
                        self.db.query(Issue.id)
                        .filter(Issue.parent_id.in_(chunk))
                        .all()
                    )
                    new_ids.update(c[0] for c in children)
                new_ids -= project_issue_ids
                project_issue_ids.update(new_ids)
                frontier = list(new_ids)

            if project_issue_ids:
                project_ids_list = list(project_issue_ids)
                proj_rows: list[tuple[str, int | None]] = []
                for i in range(0, len(project_ids_list), CHUNK):
                    chunk = project_ids_list[i : i + CHUNK]
                    proj_rows.extend(
                        self.db.query(
                            Worklog.employee_id,
                            func.sum(Worklog.time_spent_seconds).label("secs"),
                        )
                        .join(Issue, Issue.id == Worklog.issue_id)
                        .filter(
                            Worklog.employee_id.in_(emp_ids_list),
                            Worklog.issue_id.in_(chunk),
                            Worklog.started_at >= start_dt,
                            Worklog.started_at <= end_dt,
                            Issue.include_in_analysis != False,  # noqa: E712
                        )
                        .group_by(Worklog.employee_id)
                        .all()
                    )
                for emp_id, secs in proj_rows:
                    h = (secs or 0) / 3600.0
                    fact_per_emp_wt.setdefault(emp_id, {})
                    fact_per_emp_wt[emp_id][project_wt.id] = (
                        fact_per_emp_wt[emp_id].get(project_wt.id, 0.0) + h
                    )

        # 9. Группировка по роли
        employees_by_role: dict[str | None, list[Employee]] = {}
        for emp in employees:
            employees_by_role.setdefault(emp.role, []).append(emp)

        role_order_codes = [r.code for r in roles_db]
        iter_codes = role_order_codes + [c for c in employees_by_role.keys() if c not in role_order_codes]

        roles_out: list[NormWorkRoleGroup] = []
        grand_plan = 0.0
        grand_fact = 0.0

        for role_code in iter_codes:
            if role_code not in employees_by_role:
                continue
            emps = employees_by_role[role_code]
            role_obj = role_by_code.get(role_code) if role_code else None
            role_label = role_obj.label if role_obj else (role_code or "Без роли")
            role_color = role_obj.color if role_obj else "#7e94b8"

            emp_with_totals = []
            for emp in emps:
                plan_total = sum(plan_per_emp_wt.get(emp.id, {}).values())
                fact_total = sum(fact_per_emp_wt.get(emp.id, {}).values())
                pct = (fact_total / plan_total * 100) if plan_total > 0 else 0.0
                emp_with_totals.append((emp, plan_total, fact_total, pct))

            emp_with_totals.sort(key=lambda x: -x[3])

            emp_items: list[NormWorkEmployee] = []
            role_plan = 0.0
            role_fact = 0.0
            role_foreign = 0.0

            for emp, plan_total, fact_total, emp_pct in emp_with_totals:
                wt_breakdowns: list[NormWorkTypeBreakdown] = []
                for wt in work_types:
                    p = plan_per_emp_wt.get(emp.id, {}).get(wt.id, 0.0)
                    f = fact_per_emp_wt.get(emp.id, {}).get(wt.id, 0.0)
                    if p == 0 and f == 0:
                        continue
                    wt_pct = (f / p * 100) if p > 0 else 0.0
                    wt_breakdowns.append(NormWorkTypeBreakdown(
                        work_type_id=wt.id,
                        work_type_code=wt.code,
                        label=wt.label,
                        plan_hours=round(p, 1),
                        fact_hours=round(f, 1),
                        pct=round(wt_pct, 1),
                    ))

                # Виртуальная orphan-строка вставляется ПЕРЕД other_foreign
                # (либо в конец, если other_foreign в этом блоке нет).
                orphan_fact = fact_per_emp_wt.get(emp.id, {}).get(ORPHAN_WT_ID, 0.0)
                if orphan_fact > 0:
                    other_foreign_idx = next(
                        (i for i, b in enumerate(wt_breakdowns)
                         if other_foreign_wt is not None
                         and b.work_type_id == other_foreign_wt.id),
                        len(wt_breakdowns),
                    )
                    wt_breakdowns.insert(other_foreign_idx, NormWorkTypeBreakdown(
                        work_type_id=ORPHAN_WT_ID,
                        work_type_code=ORPHAN_WT_ID,
                        label=ORPHAN_WT_LABEL,
                        plan_hours=0.0,
                        fact_hours=round(orphan_fact, 1),
                        pct=0.0,
                    ))

                emp_foreign = foreign_fact_per_emp.get(emp.id, 0.0)
                emp_foreign_pct = (emp_foreign / fact_total * 100) if fact_total > 0 else 0.0

                emp_items.append(NormWorkEmployee(
                    employee_id=emp.id,
                    name=emp.display_name or "",
                    initials=_initials(emp.display_name or ""),
                    plan_hours=round(plan_total, 1),
                    fact_hours=round(fact_total, 1),
                    pct=round(emp_pct, 1),
                    foreign_hours=round(emp_foreign, 1),
                    foreign_pct=round(emp_foreign_pct, 1),
                    work_types=wt_breakdowns,
                ))
                role_plan += plan_total
                role_fact += fact_total
                role_foreign += emp_foreign

            role_pct = (role_fact / role_plan * 100) if role_plan > 0 else 0.0
            role_foreign_pct = (role_foreign / role_fact * 100) if role_fact > 0 else 0.0
            roles_out.append(NormWorkRoleGroup(
                role_code=role_code or "_unassigned",
                role_label=role_label,
                role_color=role_color,
                employees_count=len(emp_items),
                total_plan=round(role_plan, 1),
                total_fact=round(role_fact, 1),
                total_pct=round(role_pct, 1),
                foreign_hours=round(role_foreign, 1),
                foreign_pct=round(role_foreign_pct, 1),
                employees=emp_items,
            ))
            grand_plan += role_plan
            grand_fact += role_fact

        grand_pct = (grand_fact / grand_plan * 100) if grand_plan > 0 else 0.0
        grand_foreign = sum(r.foreign_hours for r in roles_out)
        grand_foreign_pct = (grand_foreign / grand_fact * 100) if grand_fact > 0 else 0.0

        return DashboardNormWorkResponse(
            roles=roles_out,
            total_plan=round(grand_plan, 1),
            total_fact=round(grand_fact, 1),
            total_pct=round(grand_pct, 1),
            foreign_hours=round(grand_foreign, 1),
            foreign_pct=round(grand_foreign_pct, 1),
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

        # Сотрудники команды + дата последнего ворклога (за всё время, не только период)
        employees_activity = self._employees_last_worklog(teams)

        return DashboardCategoriesResponse(
            items=items,
            total_hours=total_hours,
            employees=employees_activity,
        )

    def _employees_last_worklog(
        self,
        teams: Optional[list[str]] = None,
    ) -> list[EmployeeWorklogActivity]:
        """Активные сотрудники команды + дата последнего зарегистрированного ворклога."""
        emp_q = self.db.query(Employee).filter(Employee.is_active.is_(True))
        if teams:
            named_teams = [t for t in teams if t != NO_TEAM_TOKEN]
            has_none = NO_TEAM_TOKEN in teams
            clauses: list = []
            if named_teams:
                in_team_subq = (
                    select(EmployeeTeam.employee_id)
                    .where(EmployeeTeam.team.in_(named_teams))
                    .scalar_subquery()
                )
                clauses.append(Employee.id.in_(in_team_subq))
            if has_none:
                clauses.append(
                    ~exists().where(EmployeeTeam.employee_id == Employee.id)
                )
            if clauses:
                emp_q = emp_q.filter(
                    or_(*clauses) if len(clauses) > 1 else clauses[0]
                )
        employees: list[Employee] = emp_q.all()
        if not employees:
            return []

        emp_ids = [e.id for e in employees]
        last_rows = (
            self.db.query(
                Worklog.employee_id,
                func.max(Worklog.started_at).label("last_at"),
            )
            .filter(Worklog.employee_id.in_(emp_ids))
            .group_by(Worklog.employee_id)
            .all()
        )
        last_by_emp: dict[str, datetime] = {r.employee_id: r.last_at for r in last_rows}

        today = date.today()

        # Текущие отсутствия сотрудников (сегодня внутри [start_date, end_date])
        absence_rows = (
            self.db.query(Absence.employee_id, AbsenceReason.label)
            .join(AbsenceReason, Absence.reason_id == AbsenceReason.id)
            .filter(
                Absence.employee_id.in_(emp_ids),
                Absence.start_date <= today,
                Absence.end_date >= today,
            )
            .all()
        )
        absence_by_emp: dict[str, str] = {row.employee_id: row.label for row in absence_rows}

        result: list[EmployeeWorklogActivity] = []
        for emp in employees:
            last_at = last_by_emp.get(emp.id)
            days = (today - last_at.date()).days if last_at else None
            absence_label = absence_by_emp.get(emp.id)
            result.append(EmployeeWorklogActivity(
                employee_id=emp.id,
                name=emp.display_name or "",
                initials=_initials(emp.display_name or ""),
                last_worklog_at=last_at,
                days_since_last=days,
                is_absent=absence_label is not None,
                absence_label=absence_label,
            ))

        # Сортировка: stale-first; отсутствующие — в конец (отдельная группа после всех)
        result.sort(key=lambda r: (
            r.is_absent,
            r.days_since_last is None,
            -(r.days_since_last or 0),
        ))
        return result


    def get_hierarchical_report(
        self,
        year: int,
        quarter: int,
        month: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        teams: Optional[list[str]] = None,
        employee_id: Optional[str] = None,
        task_query: Optional[str] = None,
        work_type_codes: Optional[list[str]] = None,
        category_codes: Optional[list[str]] = None,
    ) -> "AnalyticsReportResponse":
        """Иерархический отчёт: Команда → Роль → Сотрудник → ВидРабот → Категория → Задача."""
        from app.schemas.analytics_report import (
            AnalyticsReportResponse, AnalyticsTeamNode, AnalyticsRoleNode,
            AnalyticsEmployeeNode, AnalyticsWorkTypeNode, AnalyticsCategoryNode,
            AnalyticsIssueNode, NodeTotals,
        )
        from app.models.employee_team import EmployeeTeam

        # 1. Период (приоритет start_date/end_date > month > quarter)
        if start_date and end_date:
            period_start, period_end = start_date, end_date
        else:
            period_start, period_end = quarter_to_dates(year, quarter, month)
        start_dt = datetime.combine(period_start, datetime.min.time())
        end_dt = datetime.combine(period_end, datetime.max.time())

        # 2. Справочники
        work_types: list[MandatoryWorkType] = (
            self.db.query(MandatoryWorkType)
            .filter(MandatoryWorkType.is_active.is_(True))
            .order_by(MandatoryWorkType.sort_order)
            .all()
        )
        wt_by_id = {wt.id: wt for wt in work_types}
        other_foreign_wt = next((wt for wt in work_types if wt.code == "other_foreign"), None)

        cat_rows = (
            self.db.query(Category.code, Category.work_type_id, Category.label, Category.color)
            .all()
        )
        cat_meta: dict[str, tuple[str, str, "str | None"]] = {
            r.code: (r.label, r.color or "#7e94b8", r.work_type_id) for r in cat_rows
        }
        code_to_wt = {code: meta[2] for code, meta in cat_meta.items() if meta[2]}

        roles_db = self.db.query(Role).filter(Role.is_active.is_(True)).order_by(Role.sort_order).all()
        role_by_code = {r.code: r for r in roles_db}

        ORPHAN_WT_ID = "__unmapped__"
        ORPHAN_WT_LABEL = "Не указана категория/вид работ"
        ORPHAN_CAT_CODE = None
        ORPHAN_CAT_LABEL = "Без категории"
        EXCLUDED_WT_ID = "__excluded__"
        EXCLUDED_WT_LABEL = "Исключено из анализа"

        # 3. Сотрудники + team membership.
        # Не фильтруем по is_active: неактивные могли работать в выбранном
        # периоде, факт должен быть виден. Бакет естественно отсечёт тех,
        # у кого нет ворклогов.
        emp_query = self.db.query(Employee)
        if employee_id:
            emp_query = emp_query.filter(Employee.id == employee_id)
        all_employees: list[Employee] = emp_query.all()

        # Любое членство в команде, не только primary — соответствует логике
        # дашборд-виджетов (drill-in с плитки должен находить те же часы).
        emp_team_rows = (
            self.db.query(EmployeeTeam.employee_id, EmployeeTeam.team, EmployeeTeam.is_primary)
            .filter(EmployeeTeam.employee_id.in_([e.id for e in all_employees]))
            .all()
        )
        emp_teams_all: dict[str, list[str]] = {}
        emp_primary: dict[str, str] = {}
        for r in emp_team_rows:
            emp_teams_all.setdefault(r.employee_id, []).append(r.team)
            if r.is_primary:
                emp_primary[r.employee_id] = r.team

        # team filter — сотрудник проходит, если ЛЮБОЕ его членство в выбранных.
        # Атрибутирование в иерархии: primary, если он в выбранных, иначе
        # первое совпавшее членство.
        if teams:
            team_set = set(teams)
            employees = [
                e for e in all_employees
                if any(t in team_set for t in emp_teams_all.get(e.id, []))
            ]
            emp_team_by_id: dict[str, str] = {}
            for e in employees:
                primary = emp_primary.get(e.id)
                if primary and primary in team_set:
                    emp_team_by_id[e.id] = primary
                    continue
                for t in emp_teams_all.get(e.id, []):
                    if t in team_set:
                        emp_team_by_id[e.id] = t
                        break
        else:
            employees = all_employees
            emp_team_by_id = dict(emp_primary)

        if not employees:
            return AnalyticsReportResponse(
                teams=[],
                grand_totals=_empty_totals(),
            )

        # 4. Ворклоги за период с агрегацией по emp×issue
        # Issue.assignee_display_name — реальное имя поля (не assignee_name)
        _has_assignee = hasattr(Issue, "assignee_display_name")
        assignee_col = Issue.assignee_display_name if _has_assignee else None

        select_cols = [
            Worklog.employee_id,
            Worklog.issue_id,
            Issue.key,
            Issue.summary,
            Issue.status,
            Issue.status_category,
            Issue.issue_type,
            Issue.category,
            Issue.assigned_category,
            Issue.team,
            Issue.participating_teams,
            Issue.include_in_analysis,
            func.sum(Worklog.time_spent_seconds).label("secs"),
            func.count(Worklog.id).label("wl_count"),
            func.max(Worklog.started_at).label("last_at"),
        ]
        if assignee_col is not None:
            select_cols.append(assignee_col.label("assignee_name"))

        # Не фильтруем по include_in_analysis: задачи из архивных категорий
        # отдельно бакетируются как «Исключено из анализа», чтобы сумма факта
        # сотрудника соответствовала реально зарегистрированным часам в Jira.
        wl_q = (
            self.db.query(*select_cols)
            .join(Issue, Issue.id == Worklog.issue_id)
            .filter(
                Worklog.employee_id.in_([e.id for e in employees]),
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
        )
        if task_query:
            q = f"%{task_query}%"
            wl_q = wl_q.filter(or_(Issue.key.ilike(q), Issue.summary.ilike(q)))

        group_cols = [
            Worklog.employee_id, Worklog.issue_id, Issue.key, Issue.summary,
            Issue.status, Issue.status_category, Issue.issue_type, Issue.category,
            Issue.assigned_category,
            Issue.team, Issue.participating_teams, Issue.include_in_analysis,
        ]
        if assignee_col is not None:
            group_cols.append(assignee_col)

        wl_q = wl_q.group_by(*group_cols)
        wl_rows = wl_q.all()

        emp_by_id = {e.id: e for e in employees}

        # 5. Бакетируем строки по (team, role, emp, wt_id, cat_code, issue)
        bucket: dict[tuple, dict] = {}

        for row in wl_rows:
            emp_id = row.employee_id
            issue_id = row.issue_id
            cat_code = row.category
            assigned_cat = row.assigned_category
            issue_team = row.team
            parts_json = row.participating_teams
            secs = row.secs or 0
            wl_count = row.wl_count or 0
            last_at = row.last_at
            h = secs / 3600.0

            emp = emp_by_id.get(emp_id)
            if emp is None:
                continue
            emp_team = emp_team_by_id.get(emp_id)

            # Задачи из архивных категорий помечены include_in_analysis=False —
            # выносим в отдельный bucket, чтобы часы не пропадали из суммы.
            is_excluded = row.include_in_analysis is False
            is_foreign = _classify_foreign(emp_team, issue_team, parts_json)

            if is_excluded:
                wt_id = EXCLUDED_WT_ID
                cat_code_eff = ORPHAN_CAT_CODE
            else:
                # Cross-team routing: чужая задача → other_foreign work_type,
                # ЕСЛИ нет ручной assigned_category. Явная ручная категория
                # перебивает foreign-routing — отчёт показывает её под нормальным
                # work_type, а сама задача помечается флагом is_foreign для UI.
                if is_foreign and other_foreign_wt is not None and not assigned_cat:
                    wt_id = other_foreign_wt.id
                    cat_code_eff = ORPHAN_CAT_CODE
                else:
                    if cat_code is None:
                        wt_id = ORPHAN_WT_ID
                        cat_code_eff = ORPHAN_CAT_CODE
                    else:
                        mapped_wt = code_to_wt.get(cat_code)
                        if mapped_wt is None:
                            wt_id = ORPHAN_WT_ID
                            cat_code_eff = cat_code
                        else:
                            wt_id = mapped_wt
                            cat_code_eff = cat_code

            # Дополнительные фильтры
            if work_type_codes:
                wt_obj = wt_by_id.get(wt_id)
                if wt_obj:
                    wt_code = wt_obj.code
                elif wt_id == ORPHAN_WT_ID:
                    wt_code = "__unmapped__"
                elif wt_id == EXCLUDED_WT_ID:
                    wt_code = "__excluded__"
                else:
                    wt_code = None
                if wt_code not in work_type_codes:
                    continue
            if category_codes:
                # Сверяем с сырым Issue.category (как виджет дашборда),
                # а не с cat_code_eff: foreign-routing переписывает cat_code_eff
                # в None, что прятало бы legitimate строки при drill-in с плитки.
                if cat_code not in category_codes:
                    continue

            team_key = emp_team or "__no_team__"
            role_key = emp.role
            key = (team_key, role_key, emp_id, wt_id, cat_code_eff, issue_id)

            entry = bucket.get(key)
            if entry is None:
                assignee_name_val = getattr(row, "assignee_name", None)
                entry = {
                    "issue_id": issue_id, "key": row.key, "summary": row.summary,
                    "status": row.status, "status_category": row.status_category,
                    "issue_type": row.issue_type, "category": cat_code,
                    "fact_hours": 0.0, "wl_count": 0,
                    "last_at": None,
                    "assignee_name": assignee_name_val,
                    "is_foreign": is_foreign,
                    "team": issue_team,
                }
                bucket[key] = entry
            entry["fact_hours"] += h
            entry["wl_count"] += wl_count
            if last_at is not None and (entry["last_at"] is None or last_at > entry["last_at"]):
                entry["last_at"] = last_at

        # 6. Свёртка bucket → дерево
        tree: dict = {}
        for (team_k, role_k, emp_id, wt_id, cat_code, issue_id), v in bucket.items():
            tree.setdefault(team_k, {}).setdefault(role_k, {}).setdefault(emp_id, {}).setdefault(
                wt_id, {}).setdefault(cat_code, []).append(v)

        # 7. Plan-часы per emp×work_type
        plan_per_emp_wt = self._build_plan_per_emp_wt(
            year=year, quarter=quarter, month=month,
            teams=teams, employees=employees, work_types=work_types,
        )

        def calc_totals(
            rows: list[dict],
            plan_hours: "float | None" = None,
            emp_count: int = 0,
            parent_total: "float | None" = None,
            parent_fact: "float | None" = None,
        ) -> NodeTotals:
            fact = sum(r["fact_hours"] for r in rows)
            wl = sum(r["wl_count"] for r in rows)
            issues = len({r["issue_id"] for r in rows})
            avg_min = (fact * 60 / wl) if wl else 0.0
            pct_plan = (fact / plan_hours * 100) if plan_hours and plan_hours > 0 else None
            pct_total = (fact / parent_total * 100) if parent_total and parent_total > 0 else 0.0
            pct_in_group = (
                (fact / parent_fact * 100)
                if parent_fact and parent_fact > 0
                else None
            )
            foreign_rows = [r for r in rows if r.get("is_foreign")]
            foreign_hours = sum(r["fact_hours"] for r in foreign_rows)
            foreign_issue_count = len({r["issue_id"] for r in foreign_rows})
            foreign_pct = (foreign_hours / fact * 100) if fact > 0 else 0.0
            return NodeTotals(
                fact_hours=round(fact, 1),
                plan_hours=round(plan_hours, 1) if plan_hours is not None else None,
                pct_plan=round(pct_plan, 1) if pct_plan is not None else None,
                pct_total=round(pct_total, 1),
                pct_in_group=round(pct_in_group, 1) if pct_in_group is not None else None,
                worklog_count=wl,
                issue_count=issues,
                employee_count=emp_count,
                avg_worklog_minutes=round(avg_min, 1),
                foreign_issue_count=foreign_issue_count,
                foreign_hours=round(foreign_hours, 1),
                foreign_pct=round(foreign_pct, 1),
            )

        grand_total_fact = sum(v["fact_hours"] for v in bucket.values())

        # Precompute fact totals at every level for parent_fact threading.
        def _sum_rows(rows: list[dict]) -> float:
            return sum(r["fact_hours"] for r in rows)

        team_fact: dict[str, float] = {}
        role_fact: dict[tuple, float] = {}
        emp_fact: dict[tuple, float] = {}
        wt_fact: dict[tuple, float] = {}
        cat_fact: dict[tuple, float] = {}

        for _tk, _rd in tree.items():
            _t_total = 0.0
            for _rk, _ed in _rd.items():
                _r_total = 0.0
                for _eid, _wd in _ed.items():
                    _e_total = 0.0
                    for _wid, _cd in _wd.items():
                        _w_total = 0.0
                        for _cc, _il in _cd.items():
                            _c = _sum_rows(_il)
                            cat_fact[(_tk, _rk, _eid, _wid, _cc)] = _c
                            _w_total += _c
                        wt_fact[(_tk, _rk, _eid, _wid)] = _w_total
                        _e_total += _w_total
                    emp_fact[(_tk, _rk, _eid)] = _e_total
                    _r_total += _e_total
                role_fact[(_tk, _rk)] = _r_total
                _t_total += _r_total
            team_fact[_tk] = _t_total

        teams_out: list[AnalyticsTeamNode] = []
        for team_key, roles_dict in tree.items():
            team_rows: list[dict] = []
            roles_out: list[AnalyticsRoleNode] = []
            team_emp_ids: set[str] = set()
            for role_key, emps_dict in roles_dict.items():
                role_rows: list[dict] = []
                emps_out: list[AnalyticsEmployeeNode] = []
                for emp_id, wts_dict in emps_dict.items():
                    emp = emp_by_id.get(emp_id)
                    if emp is None:
                        continue
                    emp_rows: list[dict] = []
                    wts_out: list[AnalyticsWorkTypeNode] = []
                    for wt_id, cats_dict in wts_dict.items():
                        wt_rows: list[dict] = []
                        cats_out: list[AnalyticsCategoryNode] = []
                        wt_obj = wt_by_id.get(wt_id)
                        if wt_obj:
                            wt_label = wt_obj.label
                        elif wt_id == EXCLUDED_WT_ID:
                            wt_label = EXCLUDED_WT_LABEL
                        else:
                            wt_label = ORPHAN_WT_LABEL
                        for cat_code, issues_list in cats_dict.items():
                            cat_label, cat_color, _ = cat_meta.get(
                                cat_code or "", (ORPHAN_CAT_LABEL, "#7e94b8", None)
                            )
                            _cat_fact = cat_fact.get((team_key, role_key, emp_id, wt_id, cat_code))
                            issues_out: list[AnalyticsIssueNode] = []
                            for v in issues_list:
                                issues_out.append(AnalyticsIssueNode(
                                    id=v["issue_id"], key=v["key"], summary=v["summary"],
                                    status=v["status"], status_category=v["status_category"],
                                    issue_type=v["issue_type"], category=v["category"],
                                    last_worklog_at=v["last_at"],
                                    assignee_name=v.get("assignee_name"),
                                    is_foreign=v.get("is_foreign", False),
                                    team=v.get("team"),
                                    totals=calc_totals([v], parent_total=grand_total_fact,
                                                       parent_fact=_cat_fact),
                                ))
                            cats_out.append(AnalyticsCategoryNode(
                                category_code=cat_code,
                                label=cat_label, color=cat_color,
                                totals=calc_totals(
                                    issues_list,
                                    parent_total=grand_total_fact,
                                    parent_fact=wt_fact.get((team_key, role_key, emp_id, wt_id)),
                                ),
                                issues=sorted(issues_out, key=lambda x: -x.totals.fact_hours),
                            ))
                            wt_rows.extend(issues_list)
                        plan_for_wt = plan_per_emp_wt.get(emp.id, {}).get(wt_id)
                        if plan_for_wt == 0.0:
                            plan_for_wt = None
                        wts_out.append(AnalyticsWorkTypeNode(
                            work_type_id=wt_id, label=wt_label,
                            totals=calc_totals(
                                wt_rows, plan_hours=plan_for_wt,
                                parent_total=grand_total_fact,
                                parent_fact=emp_fact.get((team_key, role_key, emp_id)),
                            ),
                            categories=sorted(cats_out, key=lambda x: -x.totals.fact_hours),
                        ))
                        emp_rows.extend(wt_rows)
                    emp_plan = sum(plan_per_emp_wt.get(emp.id, {}).values())
                    emps_out.append(AnalyticsEmployeeNode(
                        employee_id=emp.id,
                        name=emp.display_name or "",
                        initials=_initials(emp.display_name or ""),
                        totals=calc_totals(
                            emp_rows,
                            plan_hours=emp_plan if emp_plan > 0 else None,
                            emp_count=1,
                            parent_total=grand_total_fact,
                            parent_fact=role_fact.get((team_key, role_key)),
                        ),
                        work_types=sorted(wts_out, key=lambda x: -x.totals.fact_hours),
                    ))
                    role_rows.extend(emp_rows)
                    team_emp_ids.add(emp.id)
                role_plan = sum(
                    sum(plan_per_emp_wt.get(eid, {}).values())
                    for eid in emps_dict.keys()
                )
                role_obj = role_by_code.get(role_key)
                role_label = role_obj.label if role_obj else (role_key or "Без роли")
                role_color_main = role_obj.color if role_obj else "#7e94b8"
                roles_out.append(AnalyticsRoleNode(
                    role_code=role_key,
                    role_label=role_label, role_color=role_color_main,
                    totals=calc_totals(
                        role_rows,
                        plan_hours=role_plan if role_plan > 0 else None,
                        emp_count=len(emps_out),
                        parent_total=grand_total_fact,
                        parent_fact=team_fact.get(team_key),
                    ),
                    employees=sorted(emps_out, key=lambda x: -x.totals.fact_hours),
                ))
                team_rows.extend(role_rows)
            team_plan = sum(
                sum(plan_per_emp_wt.get(eid, {}).values())
                for roles_d in roles_dict.values()
                for eid in roles_d.keys()
            )
            teams_out.append(AnalyticsTeamNode(
                team=team_key if team_key != "__no_team__" else None,
                totals=calc_totals(
                    team_rows,
                    plan_hours=team_plan if team_plan > 0 else None,
                    emp_count=len(team_emp_ids),
                    parent_total=grand_total_fact,
                    parent_fact=grand_total_fact,
                ),
                roles=sorted(roles_out, key=lambda x: -x.totals.fact_hours),
            ))

        teams_out.sort(key=lambda t: -t.totals.fact_hours)
        all_emp_ids: set[str] = set()
        for t in tree.values():
            for r in t.values():
                for eid in r.keys():
                    all_emp_ids.add(eid)
        grand_plan = sum(
            sum(plan_per_emp_wt.get(eid, {}).values())
            for eid in all_emp_ids
        )
        total_wl = sum(v["wl_count"] for v in bucket.values())
        all_rows = list(bucket.values())
        all_foreign = [r for r in all_rows if r.get("is_foreign")]
        grand_foreign_hours = sum(r["fact_hours"] for r in all_foreign)
        grand_foreign_issues = len({r["issue_id"] for r in all_foreign})
        grand_foreign_pct = (
            (grand_foreign_hours / grand_total_fact * 100)
            if grand_total_fact > 0 else 0.0
        )
        return AnalyticsReportResponse(
            teams=teams_out,
            grand_totals=NodeTotals(
                fact_hours=round(grand_total_fact, 1),
                plan_hours=round(grand_plan, 1) if grand_plan > 0 else None,
                pct_plan=round(grand_total_fact / grand_plan * 100, 1) if grand_plan > 0 else None,
                pct_total=100.0 if grand_total_fact > 0 else 0.0,
                pct_in_group=100.0 if grand_total_fact > 0 else None,
                worklog_count=total_wl,
                issue_count=len({v["issue_id"] for v in bucket.values()}),
                employee_count=len(all_emp_ids),
                avg_worklog_minutes=round(
                    (grand_total_fact * 60 / total_wl)
                    if total_wl else 0.0,
                    1,
                ),
                foreign_issue_count=grand_foreign_issues,
                foreign_hours=round(grand_foreign_hours, 1),
                foreign_pct=round(grand_foreign_pct, 1),
            ),
        )

    def get_issue_worklogs(
        self, issue_id: str, start: date, end: date,
    ) -> list:
        """Плоский список ворклогов по задаче за период."""
        from app.schemas.analytics_report import IssueWorklogItem
        start_dt = datetime.combine(start, datetime.min.time())
        end_dt = datetime.combine(end, datetime.max.time())
        rows = (
            self.db.query(
                Worklog.id, Worklog.started_at, Worklog.hours,
                Employee.display_name, Worklog.comment_text,
            )
            .join(Employee, Employee.id == Worklog.employee_id)
            .filter(
                Worklog.issue_id == issue_id,
                Worklog.started_at >= start_dt,
                Worklog.started_at <= end_dt,
            )
            .order_by(Worklog.started_at)
            .all()
        )
        return [
            IssueWorklogItem(
                worklog_id=r.id, started_at=r.started_at, hours=r.hours or 0.0,
                employee_name=r.display_name or "", comment=r.comment_text,
            )
            for r in rows
        ]
