"""add issue participating_teams

Revision ID: 4669ffaff6ba
Revises: 007_issue_tree_fields
Create Date: 2026-04-17 10:48:33.357398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4669ffaff6ba'
down_revision: Union[str, None] = '007_issue_tree_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('participating_teams', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('participating_teams')
