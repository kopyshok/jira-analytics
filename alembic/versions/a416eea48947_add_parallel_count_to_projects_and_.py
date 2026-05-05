"""add parallel_count to projects and backlog_items

Revision ID: a416eea48947
Revises: 050_add_involvement_duration_to_backlog_items
Create Date: 2026-05-06 00:06:03.154927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a416eea48947'
down_revision: Union[str, None] = '050_add_involvement_duration_to_backlog_items'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("parallel_count_analyst", sa.Integer(), nullable=True, server_default="1"))
        batch_op.add_column(sa.Column("parallel_count_dev", sa.Integer(), nullable=True, server_default="1"))
        batch_op.add_column(sa.Column("parallel_count_qa", sa.Integer(), nullable=True, server_default="1"))

    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.add_column(sa.Column("parallel_count_analyst", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parallel_count_dev", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parallel_count_qa", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.drop_column("parallel_count_qa")
        batch_op.drop_column("parallel_count_dev")
        batch_op.drop_column("parallel_count_analyst")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("parallel_count_qa")
        batch_op.drop_column("parallel_count_dev")
        batch_op.drop_column("parallel_count_analyst")
