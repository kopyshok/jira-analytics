"""WorklogQualityRule model - rules for detecting questionable worklogs."""

from typing import Optional

from sqlalchemy import Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class WorklogQualityRule(Base, TimestampMixin):
    """Правило выявления сомнительных worklog.

    Используется для категории «незаполненные / сомнительные worklog».
    Примеры: отсутствие описания, слишком короткий текст комментария,
    отсутствие привязки к корневому эпику.
    """

    __tablename__ = "worklog_quality_rules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    rule_code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    threshold_value: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<WorklogQualityRule {self.rule_code} enabled={self.is_enabled}>"
