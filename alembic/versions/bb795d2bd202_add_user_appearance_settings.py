"""add user appearance settings

Revision ID: bb795d2bd202
Revises: c565facb3abc
Create Date: 2026-05-12 10:00:19.741215

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bb795d2bd202'
down_revision: Union[str, None] = 'c565facb3abc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('appearance_settings', sa.Text(), server_default='{}', nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('appearance_settings')
