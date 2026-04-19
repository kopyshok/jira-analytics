"""Норма рабочих часов в производственном календаре.

Revision ID: 017_production_calendar_hours
Revises: 016_production_calendar
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "017_production_calendar_hours"
down_revision: Union[str, None] = "016_production_calendar"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("production_calendar_day") as batch_op:
        batch_op.add_column(
            sa.Column("hours", sa.Float(), nullable=False, server_default="0"),
        )
    op.execute(
        """
        UPDATE production_calendar_day
        SET hours = CASE
            WHEN kind = 'preholiday' THEN 7
            WHEN kind IN ('workday', 'workday_moved') THEN 8
            WHEN is_workday = 1 THEN 8
            ELSE 0
        END
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("production_calendar_day") as batch_op:
        batch_op.drop_column("hours")
