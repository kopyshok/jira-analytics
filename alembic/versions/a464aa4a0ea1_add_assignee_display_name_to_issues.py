"""add assignee_display_name to issues

Revision ID: a464aa4a0ea1
Revises: 77ed7f5072fd
Create Date: 2026-04-22 08:38:36.227956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a464aa4a0ea1'
down_revision: Union[str, None] = '77ed7f5072fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assignee_display_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('assignee_display_name')
