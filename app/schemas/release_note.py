"""Pydantic-схемы ReleaseNote."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ReleaseNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version: str | None
    note_type: str
    section: str
    title: str
    description: str
    help_link: str | None
    is_hidden: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ReleaseNoteCreate(BaseModel):
    note_type: str
    section: str
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    help_link: str | None = None


class ReleaseNoteUpdate(BaseModel):
    note_type: str | None = None
    section: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, min_length=1)
    help_link: str | None = None
    is_hidden: bool | None = None
    sort_order: int | None = None


class VersionFeed(BaseModel):
    version: str
    notes: list[ReleaseNoteResponse]


class UnreadResponse(BaseModel):
    unread_versions: list[str]
    feeds: list[VersionFeed]


class MarkSeenRequest(BaseModel):
    version: str
