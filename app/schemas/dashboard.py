from pydantic import BaseModel


# ── Widget 1: Projects overview ──────────────────────────────────────────────

class ProjectAttentionItem(BaseModel):
    issue_key: str
    title: str
    fact_hours: float
    days_overdue: int | None   # None если не просрочен
    days_silent: int | None    # None если была активность недавно


class ProjectOverrunItem(BaseModel):
    issue_key: str
    title: str
    plan_hours: float
    fact_hours: float
    delta_hours: float         # fact - plan


class DashboardProjectsResponse(BaseModel):
    total: int
    done: int
    in_progress: int
    overdue: int
    not_started: int
    forecast_done: int         # прогноз: сколько закроется к концу квартала
    forecast_pct: float        # forecast_done / total * 100
    attention_list: list[ProjectAttentionItem]
    overrun_list: list[ProjectOverrunItem]


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
