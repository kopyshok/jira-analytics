"""add_selected_theme_to_users

Revision ID: c23571f86b16
Revises: 11fe1c4e0e94
Create Date: 2026-05-07 15:31:40.858849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c23571f86b16'
down_revision: Union[str, None] = '11fe1c4e0e94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'selected_theme',
            sa.String(20),
            nullable=False,
            server_default='dark-blue',
        ))


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('selected_theme')
