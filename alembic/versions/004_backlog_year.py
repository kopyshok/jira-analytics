"""Add year column to backlog_items

Revision ID: 004_backlog_year
Revises: 003_scope_categories_planning
Create Date: 2026-04-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004_backlog_year'
down_revision: Union[str, None] = '003_scope_categories_planning'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('backlog_items') as batch_op:
        batch_op.add_column(sa.Column('year', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('backlog_items') as batch_op:
        batch_op.drop_column('year')
