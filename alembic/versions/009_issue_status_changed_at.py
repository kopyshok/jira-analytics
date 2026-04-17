"""add issue.status_changed_at

Revision ID: 009_issue_status_changed_at
Revises: 008_archive_rfa_categories
Create Date: 2026-04-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '009_issue_status_changed_at'
down_revision: Union[str, None] = '008_archive_rfa_categories'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status_changed_at', sa.DateTime(), nullable=True))
        batch_op.create_index(
            op.f('ix_issues_status_changed_at'),
            ['status_changed_at'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_issues_status_changed_at'))
        batch_op.drop_column('status_changed_at')
