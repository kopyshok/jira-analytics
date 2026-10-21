"""Старая учётка Jira, слитая с другим сотрудником."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class EmployeeAccountAlias(Base, TimestampMixin):
    """Учётка Jira лишней карточки после объединения сотрудников.

    Синк встречает её в авторах списаний, исполнителях и разработчиках задач
    и подставляет сотрудника, в которого карточку влили, — иначе двойник
    заводился бы заново при первом же чтении старых записей.
    """

    __tablename__ = "employee_account_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    jira_account_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    employee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
