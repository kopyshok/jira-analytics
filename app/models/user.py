import json
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class UserRole(str, PyEnum):
    admin = "admin"
    super_manager = "super_manager"
    manager = "manager"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False), nullable=False
    )
    default_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selected_teams_raw: Mapped[str] = mapped_column(
        "selected_teams", Text, nullable=False, default="[]"
    )

    @property
    def selected_teams(self) -> list[str]:
        try:
            return json.loads(self.selected_teams_raw or "[]")
        except (TypeError, ValueError):
            return []

    @selected_teams.setter
    def selected_teams(self, value: list[str]) -> None:
        self.selected_teams_raw = json.dumps(list(value or []))
