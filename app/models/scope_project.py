"""ScopeProject model - allowed Jira projects for data loading."""

from typing import Optional

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base


class ScopeProject(Base, TimestampMixin):
    """Разрешённый проект Jira для загрузки данных.

    Без включения проекта в scope данные из него не загружаются.
    Пользователь обязан настроить scope перед первой синхронизацией.
    """

    __tablename__ = "scope_projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    jira_project_key: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )
    jira_project_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<ScopeProject {self.jira_project_key} enabled={self.is_enabled}>"
