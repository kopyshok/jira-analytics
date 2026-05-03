"""add_pert_multipliers

Revision ID: d9ef5e667679
Revises: 86308219f1e6
Create Date: 2026-05-03 23:24:12.567565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9ef5e667679'
down_revision: Union[str, None] = '86308219f1e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(sa.Column(
            "optimistic_multiplier", sa.Float(),
            nullable=False, server_default="0.7",
        ))
        batch.add_column(sa.Column(
            "pessimistic_multiplier", sa.Float(),
            nullable=False, server_default="1.5",
        ))


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("pessimistic_multiplier")
        batch.drop_column("optimistic_multiplier")
