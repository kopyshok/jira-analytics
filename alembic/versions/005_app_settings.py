"""Add app_settings table

Revision ID: 005_app_settings
Revises: 004_backlog_year
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005_app_settings'
down_revision: Union[str, None] = '004_backlog_year'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('key', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
