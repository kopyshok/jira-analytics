"""executive_snapshot

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-05-08 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1b2c3d4e5f60'
down_revision: Union[str, None] = '0a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'executive_dashboard_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=False),
        sa.Column('team_set_hash', sa.String(32), nullable=False),
        sa.Column('team_set_json', sa.Text(), nullable=False),
        sa.Column('snapshot_data', sa.Text(), nullable=False),
        sa.Column('model_id', sa.String(120), nullable=True),
        sa.Column('prompt_version', sa.String(32), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            'created_by',
            sa.String(36),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.UniqueConstraint('year', 'quarter', 'team_set_hash', name='uq_exec_snap_period_team'),
    )


def downgrade() -> None:
    op.drop_table('executive_dashboard_snapshots')
