"""Pydantic schemas для resource planning v2."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class QualityMetricSchema(BaseModel):
    plan_id: str
    overload_days_pct: float
    late_count: int
    mean_utilization_pct: float
    computed_at: datetime


class PhaseAllocationSchema(BaseModel):
    phase: Literal["analyst", "dev", "qa", "opo"]
    hours: float
    employee_id: Optional[str]
    start_date: date
    end_date: date


class SolverAssignmentSchema(BaseModel):
    backlog_item_id: str
    assignee_employee_id: Optional[str]
    start_date: date
    end_date: date
    phase_breakdown: list[PhaseAllocationSchema] = Field(default_factory=list)


class SolverResultSchema(BaseModel):
    assignments: list[SolverAssignmentSchema]
    infeasible_items: list[str] = Field(default_factory=list)
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE"]
    solve_time_ms: int


class OptimizeResponse(BaseModel):
    new_plan_id: str
    before: QualityMetricSchema
    after: QualityMetricSchema
    solver_status: Literal["OPTIMAL", "FEASIBLE", "INFEASIBLE"]
    solve_time_ms: int
    infeasible_items: list[str]
