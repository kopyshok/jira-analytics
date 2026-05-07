"""Pydantic schemas for thematic work-type report."""
from datetime import datetime
from typing import Optional

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
    created_at: datetime
    updated_at: datetime


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
