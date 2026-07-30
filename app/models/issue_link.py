"""Связь между задачами Jira. Нужна KPI: баг привязан к задаче, автор которой оценивается."""
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class IssueLink(Base, TimestampMixin):
    """Направленная связь: source → target, тип из Jira ('Relates', 'Blocks', ...)."""

    __tablename__ = "issue_links"
    __table_args__ = (
        UniqueConstraint(
            "source_issue_id", "target_issue_id", "link_type", name="uq_issue_link"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_issue_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<IssueLink {self.source_issue_id} -{self.link_type}-> {self.target_issue_id}>"
