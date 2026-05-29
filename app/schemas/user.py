from __future__ import annotations
import re
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.models.user import UserRole

_HEX_COLOR_RE = re.compile(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def _validate_hex(v: str) -> str:
    if not _HEX_COLOR_RE.match(v):
        raise ValueError(f"Некорректный HEX-цвет: {v!r}. Ожидается #rgb или #rrggbb.")
    return v


class AppearanceSettings(BaseModel):
    phase_colors: dict[str, str] = Field(default_factory=lambda: {
        "analyst": "#00c9c8",
        "dev": "#2a7fbf",
        "qa": "#e8864a",
        "opo": "#52d364",
    })
    initiative_bracket_color: str = "#b8c9e0"
    initiative_fill_intensity: Literal["soft", "medium", "dense"] = "medium"
    animation_speed_seconds: float = Field(default=4.0, ge=0.5, le=20.0)

    @field_validator("phase_colors")
    @classmethod
    def validate_phase_colors(cls, v: dict[str, str]) -> dict[str, str]:
        for key, color in v.items():
            _validate_hex(color)
        return v

    @field_validator("initiative_bracket_color")
    @classmethod
    def validate_bracket_color(cls, v: str) -> str:
        return _validate_hex(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: UserRole
    default_team: str | None
    selected_teams: list[str] = []
    selected_theme: str = "dark-blue"
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("selected_theme", mode="before")
    @classmethod
    def _default_theme(cls, v: str | None) -> str:
        # Свежесозданный User-объект до flush'а имеет `selected_theme=None`,
        # SQL-default «dark-blue» применяется только в БД.
        return v if v else "dark-blue"


class UserCreate(BaseModel):
    email: str
    password: str
    display_name: str
    role: UserRole
    default_team: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, v: str) -> str:
        return v.strip().lower() if isinstance(v, str) else v


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    default_team: str | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str


class UserTeamsUpdate(BaseModel):
    teams: list[str]
