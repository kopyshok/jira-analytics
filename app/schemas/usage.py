"""Pydantic schemas для usage analytics."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class UsageEventIn(BaseModel):
    event_type: Literal["page_view", "heartbeat", "action"]
    path: str = Field(..., max_length=255)
    action_type: str | None = Field(None, max_length=64)
    entity_id: str | None = Field(None, max_length=36)
    at: datetime


class UsageEventBatchIn(BaseModel):
    events: list[UsageEventIn] = Field(..., max_length=100)


class UsageBatchResult(BaseModel):
    accepted: int
    rejected: int


class UsageOverviewOut(BaseModel):
    dau: int
    wau: int
    mau: int
    hours_30d: float


class UsageUserRowOut(BaseModel):
    user_id: str
    display_name: str
    role: str
    last_seen: datetime | None
    active_days: int
    hours: float
    top_path: str | None


class UsagePageRowOut(BaseModel):
    path: str
    unique_users: int
    views: int
    hours: float


class UsageMatrixCellOut(BaseModel):
    user_id: str
    display_name: str
    path: str
    hours: float


class UsageMatrixOut(BaseModel):
    users: list[dict]
    paths: list[dict]
    cells: list[UsageMatrixCellOut]


class UsageTimelinePointOut(BaseModel):
    date: date
    views: int
    active_users: int
    seconds: int


class UsageActionRowOut(BaseModel):
    action_type: str
    total: int
    top_users: list[dict]
