"""ConfluencePageCache — кэш Confluence-страниц для AI-саммари."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, generate_uuid


class ConfluencePageCache(Base, TimestampMixin):
    """Кэш текста Confluence-страниц по page_id.

    Используется в `ConfluenceService` для подмешивания текста ТЗ в промпт LLM.
    """

    __tablename__ = "confluence_page_cache"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    page_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
