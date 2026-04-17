"""Sync state for incremental Jira synchronization."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class SyncState(Base, TimestampMixin):
    """Tracks synchronization state for incremental updates.

    Unique by ``(entity_name, scope)``. ``scope=""`` is the default for
    global entity cursors (``"issues"``, ``"worklogs"``, ...). Team-scoped
    cursors store the team name in ``scope`` (e.g.
    ``entity_name="issues", scope="Team X"``) so per-team intraday sync
    has its own independent watermark.
    """

    __tablename__ = "sync_state"
    __table_args__ = (
        UniqueConstraint("entity_name", "scope", name="uq_sync_state_entity_scope"),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )

    # Entity being synced (e.g., "issues", "worklogs", "projects")
    entity_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    # Scope discriminator: "" for global, team name for per-team cursors.
    scope: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        server_default="",
        index=True,
    )

    # Last successful sync timestamp
    last_success_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Cursor value for pagination
    cursor_value: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Last error message if sync failed
    last_error: Mapped[Optional[str]] = mapped_column(
        String(2000),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<SyncState {self.entity_name}[{self.scope}]: {self.last_success_at}>"
