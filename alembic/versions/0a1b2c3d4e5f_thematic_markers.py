"""thematic_markers

Adds markers (JSON), area (string), nature (string) columns to
issue_classifications. Bumps prompt cache via PROMPT_VERSION change in code.

Revision ID: 0a1b2c3d4e5f
Revises: 4c22dff2526e
Create Date: 2026-05-08 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0a1b2c3d4e5f'
down_revision: Union[str, None] = '4c22dff2526e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issue_classifications', schema=None) as batch_op:
        batch_op.add_column(sa.Column('markers_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('area', sa.String(120), nullable=True))
        batch_op.add_column(sa.Column('nature', sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('issue_classifications', schema=None) as batch_op:
        batch_op.drop_column('nature')
        batch_op.drop_column('area')
        batch_op.drop_column('markers_json')
