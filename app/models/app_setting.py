"""AppSetting model — key-value settings stored in DB."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class AppSetting(Base, TimestampMixin):
    """Произвольные настройки приложения (key → value)."""

    __tablename__ = "app_settings"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    key: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    value: Mapped[str] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AppSetting {self.key}>"
