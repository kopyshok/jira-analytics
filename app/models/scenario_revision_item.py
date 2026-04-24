"""ScenarioRevisionItem model — one diff entry per changed initiative per revision."""

from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TimestampMixin, generate_uuid
from app.database import Base

if TYPE_CHECKING:
    from app.models.scenario_revision import ScenarioRevision
    from app.models.backlog_item import BacklogItem


class ScenarioRevisionItem(Base, TimestampMixin):
    """Строка диффа инициатив при пересмотре сценария.

    action='included' — задача добавлена в сценарий.
    action='excluded' — задача убрана из сценария.
    backlog_item_name денормализовано на случай последующего удаления задачи.
    """

    __tablename__ = "scenario_revision_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_revisions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    backlog_item_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("backlog_items.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    backlog_item_name: Mapped[str] = mapped_column(String(500), nullable=False)
    action: Mapped[str] = mapped_column(String(8), nullable=False)

    revision: Mapped["ScenarioRevision"] = relationship(back_populates="items")
    backlog_item: Mapped[Optional["BacklogItem"]] = relationship()

    def __repr__(self) -> str:
        return f"<ScenarioRevisionItem {self.action} {self.backlog_item_name}>"
