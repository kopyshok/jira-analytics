"""UserRpPreferences — per-user UI preferences for resource-planning page."""

from typing import Dict, List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, false, true
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
        Boolean, nullable=False, default=False, server_default=false()
    )
    collapsed_initiative_ids: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    view_mode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    show_relay: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    detail_sections_visible: Mapped[Dict[str, bool]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    detail_sections_collapsed: Mapped[Dict[str, bool]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    fill_intensity_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default="50"
    )
    fill_contrast_pct: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default="50"
    )
    pulse_highlighted_employee: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    pulse_critical_path: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    out_of_quarter_months: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    hide_weekend_stripes_week_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
