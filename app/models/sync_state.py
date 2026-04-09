"""Sync state for incremental Jira synchronization."""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class SyncState(Base, TimestampMixin):
    """Tracks synchronization state for incremental updates."""
    
    __tablename__ = "sync_state"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    
    # Entity being synced (e.g., "issues", "worklogs", "projects")
    entity_name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
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
        return f"<SyncState {self.entity_name}: {self.last_success_at}>"
