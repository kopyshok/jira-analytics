"""Pydantic-схемы иерархического отчёта Аналитики."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NodeTotals(BaseModel):
    fact_hours: float
    plan_hours: Optional[float] = None
    pct_plan: Optional[float] = None
    pct_total: float
    pct_in_group: Optional[float] = None
    worklog_count: int
    issue_count: int
    employee_count: int
    avg_worklog_minutes: float
    foreign_issue_count: int = 0
    foreign_hours: float = 0.0
    foreign_pct: float = 0.0


class AnalyticsIssueNode(BaseModel):
    id: str
    key: str
    summary: str
    status: str
    status_category: Optional[str] = None
    issue_type: str
    category: Optional[str] = None
    last_worklog_at: Optional[datetime] = None
    assignee_name: Optional[str] = None
    is_foreign: bool = False
    team: Optional[str] = None
    totals: NodeTotals


class AnalyticsCategoryNode(BaseModel):
    category_code: Optional[str] = None
    label: str
    color: str
    totals: NodeTotals
    issues: list[AnalyticsIssueNode]


class AnalyticsWorkTypeNode(BaseModel):
    work_type_id: str
    label: str
    totals: NodeTotals
    categories: list[AnalyticsCategoryNode]


class AnalyticsEmployeeNode(BaseModel):
    employee_id: str
    name: str
    initials: str
    totals: NodeTotals
    work_types: list[AnalyticsWorkTypeNode]


class AnalyticsRoleNode(BaseModel):
    role_code: Optional[str] = None
    role_label: str
    role_color: str
    totals: NodeTotals
    employees: list[AnalyticsEmployeeNode]


class AnalyticsTeamNode(BaseModel):
    team: Optional[str] = None
    totals: NodeTotals
    roles: list[AnalyticsRoleNode]


class AnalyticsReportResponse(BaseModel):
    teams: list[AnalyticsTeamNode]
    grand_totals: NodeTotals


class IssueWorklogItem(BaseModel):
    worklog_id: str
    started_at: datetime
    hours: float
    employee_name: str
    comment: Optional[str] = None
