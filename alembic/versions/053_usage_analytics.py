"""usage_analytics

Revision ID: 053_usage_analytics
Revises: 052_feedback_items
Create Date: 2026-05-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "053_usage_analytics"
down_revision: Union[str, None] = "052_feedback_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_events_at", "usage_events", ["at"])
    op.create_index("ix_usage_events_user_at", "usage_events", ["user_id", "at"])
    op.create_index("ix_usage_events_at_type", "usage_events", ["at", "event_type"])
    op.create_index("ix_usage_events_path_at", "usage_events", ["path", "at"])

    op.create_table(
        "usage_daily",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("actions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "user_id", "path", name="uq_usage_daily_date_user_path"),
    )
    op.create_index("ix_usage_daily_date_user", "usage_daily", ["date", "user_id"])
    op.create_index("ix_usage_daily_date_path", "usage_daily", ["date", "path"])


def downgrade() -> None:
    op.drop_index("ix_usage_daily_date_path", table_name="usage_daily")
    op.drop_index("ix_usage_daily_date_user", table_name="usage_daily")
    op.drop_table("usage_daily")
    op.drop_index("ix_usage_events_path_at", table_name="usage_events")
    op.drop_index("ix_usage_events_at_type", table_name="usage_events")
    op.drop_index("ix_usage_events_user_at", table_name="usage_events")
    op.drop_index("ix_usage_events_at", table_name="usage_events")
    op.drop_table("usage_events")
