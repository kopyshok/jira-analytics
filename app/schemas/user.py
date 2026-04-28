from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from app.models.user import UserRole


class LoginRequest(BaseModel):
    email: str
    password: str


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
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    password: str
    display_name: str
    role: UserRole
    default_team: str | None = None


class UserUpdate(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None
    default_team: str | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: str


class UserTeamsUpdate(BaseModel):
    teams: list[str]
