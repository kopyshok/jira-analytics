"""Base model with common fields."""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column



class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SyncedMixin(TimestampMixin):
    """Mixin for entities synced from Jira."""
    
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
    )


def generate_uuid() -> str:
    """Generate a UUID string for primary keys."""
    return str(uuid.uuid4())
