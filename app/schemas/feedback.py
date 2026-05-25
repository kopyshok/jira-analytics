"""Pydantic schemas для feedback (баги + идеи)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AttachmentRef(BaseModel):
    filename: str
    mime: str
    size: int
    path: str  # storage path returned by upload endpoint


class FeedbackContext(BaseModel):
    """Авто-собранный контекст браузера (только для багов)."""

    user_agent: str | None = None
    language: str | None = None
    screen_w: int | None = None
    screen_h: int | None = None
    timezone: str | None = None
    active_team: str | None = None
    active_period: str | None = None
    theme: str | None = None
    console_errors: list[dict] = Field(default_factory=list)
    network_errors: list[dict] = Field(default_factory=list)


class BugCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    page_url: str | None = None
    steps_to_reproduce: str | None = None
    expected: str | None = None
    actual: str | None = None
    context: FeedbackContext | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)


class IdeaCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)
    page_url: str | None = None


class FeedbackAuthor(BaseModel):
    id: str
    display_name: str
    email: str


class FeedbackRead(BaseModel):
    id: str
    kind: Literal["bug", "idea"]
    author: FeedbackAuthor
    title: str
    body: str
    page_url: str | None
    read_at: datetime | None
    read_by: str | None
    steps_to_reproduce: str | None = None
    expected: str | None = None
    actual: str | None = None
    context: FeedbackContext | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MarkReadRequest(BaseModel):
    ids: list[str] = Field(..., min_length=1)


class ExportRequest(BaseModel):
    kind: Literal["bug", "idea"]
    ids: list[str] | None = None
    only_unread: bool = False
    mark_after: bool = False
