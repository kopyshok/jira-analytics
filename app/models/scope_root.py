"""ScopeRoot model - root epics/tasks for category auto-assignment."""

from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class ScopeRoot(Base, TimestampMixin):
    """Корневой эпик/задача для авто-раскладки по категориям.

    Все дочерние элементы внутри иерархии автоматически относятся
    к выбранной категории, если для них не задано переопределение.
    Поддерживает ключ или URL Jira.
    """

    __tablename__ = "scope_roots"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    category_code: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    jira_issue_key: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    jira_issue_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    project_key: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<ScopeRoot {self.category_code}: {self.jira_issue_key}>"
