"""add involvement+duration to backlog_items

Revision ID: 050_add_involvement_duration_to_backlog_items
Revises: 049_drop_result_flow_json
Create Date: 2026-05-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "050_add_involvement_duration_to_backlog_items"
down_revision: Union[str, None] = "049_drop_result_flow_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.add_column(sa.Column("involvement_analyst", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("involvement_dev", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("involvement_qa", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("involvement_launch", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("duration_analyst_days", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("duration_dev_days", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("duration_qa_days", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("duration_launch_days", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.drop_column("duration_launch_days")
        batch_op.drop_column("duration_qa_days")
        batch_op.drop_column("duration_dev_days")
        batch_op.drop_column("duration_analyst_days")
        batch_op.drop_column("involvement_launch")
        batch_op.drop_column("involvement_qa")
        batch_op.drop_column("involvement_dev")
        batch_op.drop_column("involvement_analyst")
