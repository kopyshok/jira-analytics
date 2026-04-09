"""CategoryOverride model - explicit category overrides for specific issues."""

from typing import Optional

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class CategoryOverride(Base, TimestampMixin):
    """Точечное переопределение категории для конкретной задачи.

    Нужно для исключений внутри иерархии — когда задача не должна
    наследовать категорию родительского эпика.
    """

    __tablename__ = "category_overrides"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_issue_key: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    category_code: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CategoryOverride {self.jira_issue_key} -> {self.category_code}>"
