from datetime import date

from pydantic import BaseModel


# ── Widget 1: Projects overview ──────────────────────────────────────────────

class ProjectAssignee(BaseModel):
    initials: str
    color: str  # hex, для аватара (от роли сотрудника либо генерим)


class ProjectItem(BaseModel):
    issue_key: str
    title: str
    status_category: str            # 'done' | 'indeterminate' | 'new' | 'overdue'
    plan_hours: float
    fact_hours: float
    delta_hours: float              # fact - plan
    subtasks_done: int
    subtasks_total: int
    assignees: list[ProjectAssignee]   # top-3 по часам
    assignees_total: int               # всего сотрудников касавшихся эпика
    due_date: date | None
    days_to_due: int | None            # negative = overdue, None = no due
    trend_hours_week: float            # часы за последние 7 дней
    trend_dir: str                     # 'up' | 'down' | 'flat'
    forecast_close_date: date | None
    forecast_in_quarter: bool          # успевает ли к концу квартала
    silent_days: int                   # дни с последнего ворклога (0 если был сегодня)
    weekly_activity: list[float]       # 8 точек спарклайна (часы/неделю с конца периода назад)


class DashboardProjectsResponse(BaseModel):
    total: int
    done: int
    in_progress: int
    overdue: int
    not_started: int
    total_fact_hours: float
    total_plan_hours: float
    avg_load_pct: float          # total_fact / total_plan * 100
    silent_count: int            # проекты с silent_days > 14
    forecast_done: int
    forecast_pct: float
    projects: list[ProjectItem]


# ── Widget 2: Norm work plan/fact ────────────────────────────────────────────

class NormWorkItem(BaseModel):
    work_type_id: str
    label: str
    plan_hours: float
    fact_hours: float
    pct: float                 # fact / plan * 100 (0 если plan == 0)


class DashboardNormWorkResponse(BaseModel):
    items: list[NormWorkItem]
    total_plan: float
    total_fact: float
    total_pct: float


# ── Widget 3: Category metrics ───────────────────────────────────────────────

class CategoryMetaItem(BaseModel):
    key: str
    label: str
    color: str
    hours: float
    worklog_count: int
    issue_count: int
    employee_count: int
    avg_worklog_minutes: float
    pct: float                 # от общего числа часов в периоде


class DashboardCategoriesResponse(BaseModel):
    items: list[CategoryMetaItem]
    total_hours: float
