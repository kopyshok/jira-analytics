"""UserRpPreferences — per-user UI preferences for resource-planning page."""

from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class UserRpPreferences(Base, TimestampMixin):
    """Хранит per-user настройки страницы /resource-planning.

    user_id — PK + FK на users.id (one row per user).
    """

    __tablename__ = "user_rp_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    hide_weekends: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    collapsed_initiative_ids: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    view_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    show_relay: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
