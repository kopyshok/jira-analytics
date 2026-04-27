"""Pydantic schemas for sync pipeline / runs / schedule."""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


PipelineMode = Literal["quick", "normal", "full", "team"]
SyncRunStatus = Literal["running", "ok", "partial", "failed", "cancelled", "skipped"]
SyncTrigger = Literal["manual", "scheduled"]


class PipelineRequest(BaseModel):
    mode: PipelineMode
    team: Optional[str] = None
    since: Optional[date] = None


class TeamRefreshRequest(BaseModel):
    team: str


class StageReport(BaseModel):
    stage: str
    started: datetime
    finished: Optional[datetime] = None
    status: str  # ok | partial | failed | skipped
    counts: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class SyncRunOut(BaseModel):
    id: str
    started_at: datetime
    finished_at: Optional[datetime]
    status: SyncRunStatus
    trigger: SyncTrigger
    mode: PipelineMode
    team: Optional[str]
    stages_json: list[dict]
    error_text: Optional[str]
    schedule_id: Optional[str]

    model_config = {"from_attributes": True}


class SyncScheduleOut(BaseModel):
    id: str
    name: str
    cron_expr: str
    mode: PipelineMode
    team: Optional[str]
    enabled: bool
    last_run_id: Optional[str]
    next_run_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SyncScheduleUpdate(BaseModel):
    cron_expr: Optional[str] = None
    mode: Optional[PipelineMode] = None
    team: Optional[str] = None
    enabled: Optional[bool] = None


class SyncScheduleCreate(BaseModel):
    name: str
    cron_expr: str
    mode: PipelineMode
    team: Optional[str] = None
    enabled: bool = True
