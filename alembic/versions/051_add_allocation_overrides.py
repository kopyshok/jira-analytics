"""add allocation overrides for cross-quarter re-estimate

Revision ID: c565facb3abc
Revises: d07312da3379
Create Date: 2026-05-11 18:31:22.964520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c565facb3abc'
down_revision: Union[str, None] = 'd07312da3379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scenario_allocations") as batch:
        batch.add_column(sa.Column("override_estimate_analyst_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("override_estimate_dev_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("override_estimate_qa_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("override_estimate_opo_hours", sa.Float(), nullable=True))

    with op.batch_alter_table("scenario_allocation_snapshots") as batch:
        batch.add_column(sa.Column("override_estimate_analyst_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("override_estimate_dev_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("override_estimate_qa_hours", sa.Float(), nullable=True))
        batch.add_column(sa.Column("override_estimate_opo_hours", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scenario_allocation_snapshots") as batch:
        batch.drop_column("override_estimate_opo_hours")
        batch.drop_column("override_estimate_qa_hours")
        batch.drop_column("override_estimate_dev_hours")
        batch.drop_column("override_estimate_analyst_hours")

    with op.batch_alter_table("scenario_allocations") as batch:
        batch.drop_column("override_estimate_opo_hours")
        batch.drop_column("override_estimate_qa_hours")
        batch.drop_column("override_estimate_dev_hours")
        batch.drop_column("override_estimate_analyst_hours")
