"""add parent change tracking to issue

Revision ID: ce7f3e3e1aa5
Revises: 064_backlog_team
Create Date: 2026-06-16 17:09:09.513822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ce7f3e3e1aa5'
down_revision: Union[str, None] = '064_backlog_team'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('parent_changed', sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column('category_context', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('category_context_key', sa.String(length=32), nullable=True))
        batch_op.create_index(batch_op.f('ix_issues_parent_changed'), ['parent_changed'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_issues_parent_changed'))
        batch_op.drop_column('category_context_key')
        batch_op.drop_column('category_context')
        batch_op.drop_column('parent_changed')
