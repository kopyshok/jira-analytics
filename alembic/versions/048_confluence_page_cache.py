"""add confluence_page_cache

Revision ID: 048_confluence_page_cache
Revises: 047_issue_description_extra_fields
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "048_confluence_page_cache"
down_revision: Union[str, None] = "047_issue_description_extra_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "confluence_page_cache",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("page_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("title", sa.String(512), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("error", sa.String(512), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("confluence_page_cache")
