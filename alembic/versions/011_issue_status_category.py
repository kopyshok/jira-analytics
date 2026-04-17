"""add issue.status_category

Revision ID: 011_issue_status_category
Revises: 010_archive_target_category
Create Date: 2026-04-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '011_issue_status_category'
down_revision: Union[str, None] = '010_archive_target_category'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status_category', sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('status_category')
