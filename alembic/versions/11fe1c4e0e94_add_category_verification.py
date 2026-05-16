"""add category verification fields to issues

Revision ID: 11fe1c4e0e94
Revises: a416eea48947
Create Date: 2026-05-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '11fe1c4e0e94'
down_revision: Union[str, None] = 'a416eea48947'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'category_verified',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ))
        batch_op.add_column(sa.Column(
            'require_child_verification',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ))


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('require_child_verification')
        batch_op.drop_column('category_verified')
