"""add due_date to issue

Revision ID: e97b35c021a7
Revises: 034_scenario_allocation_sort_order
Create Date: 2026-04-26 11:46:42.379414

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e97b35c021a7'
down_revision: Union[str, None] = '034_scenario_allocation_sort_order'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('due_date', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('due_date')
