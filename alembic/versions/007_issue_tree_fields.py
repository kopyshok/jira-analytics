"""Add team, assigned_category, include_in_analysis to issues

Revision ID: 007_issue_tree_fields
Revises: 006_categories
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '007_issue_tree_fields'
down_revision: Union[str, None] = '006_categories'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues') as batch_op:
        batch_op.add_column(sa.Column('team', sa.String(200), nullable=True))
        batch_op.add_column(sa.Column('assigned_category', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('include_in_analysis', sa.Boolean(), nullable=True, server_default='1'))


def downgrade() -> None:
    with op.batch_alter_table('issues') as batch_op:
        batch_op.drop_column('include_in_analysis')
        batch_op.drop_column('assigned_category')
        batch_op.drop_column('team')
