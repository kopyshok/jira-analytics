"""Production calendar — особые дни РФ.

Revision ID: 016_production_calendar
Revises: 015_main_box_container_rule
Create Date: 2026-04-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "016_production_calendar"
down_revision: Union[str, None] = "015_main_box_container_rule"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_calendar_day",
        sa.Column("date", sa.Date(), primary_key=True),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("synced_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("production_calendar_day")
