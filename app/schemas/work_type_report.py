"""Pydantic schemas for thematic work-type report."""
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---- Themes ----

class ThemeBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    color: str = Field(default="#00c9c8", pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: int = 0


class ThemeCreateRequest(ThemeBase):
    work_type_id: str


class ThemeUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    sort_order: Optional[int] = None


class ThemeMergeRequest(BaseModel):
    target_theme_id: str


class ThemeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    work_type_id: str
    name: str
    description: Optional[str]
    color: str
    sort_order: int
    is_archived: bool
    aliases: list[str] = []
    created_at: datetime
    updated_at: datetime


class AliasAddRequest(BaseModel):
    alias: str = Field(..., min_length=1, max_length=255)


class ThemeAliasResponse(BaseModel):
    theme_id: str
    aliases: list[str]


class ThresholdResponse(BaseModel):
    threshold: float


class ThresholdRequest(BaseModel):
    threshold: float = Field(..., ge=0.0, le=1.0)


class ThemeCandidate(BaseModel):
    """Кандидат в словарь — из ведра «Другое» свежего снапшота."""
    proposed_name: str
    issues_count: int
    hours: float
    sample_keys: list[str]
    snapshot_id: str


class ThemeListResponse(BaseModel):
    themes: list[ThemeOut]
    candidates: list[ThemeCandidate]


# ---- Report ----

class WorkTypeReportRequest(BaseModel):
    work_type_id: str
    year: int = Field(..., ge=2020, le=2100)
    quarter: int = Field(..., ge=1, le=4)
    month: Optional[int] = Field(None, ge=1, le=12)
    teams: list[str] = []
    force_refresh: bool = False


class WorkTypeReportResponse(BaseModel):
    snapshot_id: str
    work_type_id: str
    year: int
    quarter: int
    month: Optional[int]
    start_date: date
    end_date: date
    team_set: list[str]
    generated_at: datetime
    model_id: Optional[str]
    prompt_version: Optional[str]
    dictionary_version: int
    is_stale: bool
    data: dict[str, Any]


class CandidateAcceptRequest(BaseModel):
    snapshot_id: str
    proposed_name: str
    new_theme_name: Optional[str] = None
    color: str = Field(default="#00c9c8", pattern=r"^#[0-9A-Fa-f]{6}$")


class CandidateMergeRequest(BaseModel):
    snapshot_id: str
    proposed_name: str
    target_theme_id: str


class CandidateIgnoreRequest(BaseModel):
    snapshot_id: str
    proposed_name: str


class ManualClassifyRequest(BaseModel):
    issue_id: str
    work_type_id: str
    theme_id: Optional[str]   # None = leave unclassified
    contribution_text: Optional[str] = None


# ---- Layouts ----

class LayoutBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    grouping_dims: list[Literal["theme", "team", "role", "employee", "project", "issue"]]
    visible_columns: Optional[list[str]] = None
    is_default: bool = False


class LayoutCreateRequest(LayoutBase):
    work_type_id: str


class LayoutUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    grouping_dims: Optional[list[Literal["theme", "team", "role", "employee", "project", "issue"]]] = None
    visible_columns: Optional[list[str]] = None
    is_default: Optional[bool] = None


class LayoutOut(LayoutBase):
    model_config = ConfigDict(from_attributes=True)
    id: str
    user_id: str
    work_type_id: str
    created_at: datetime
    updated_at: datetime
