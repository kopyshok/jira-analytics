"""add sync_state.scope for per-team cursors

Revision ID: 013_sync_state_scope
Revises: 012_issue_goals
Create Date: 2026-04-17

Adds a ``scope`` column to ``sync_state`` so we can track per-team
intraday sync cursors independently from the global ``issues`` cursor.
Existing rows get ``scope=""`` (the "global" bucket). Replaces the
unique constraint on ``entity_name`` alone with a composite
``(entity_name, scope)``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '013_sync_state_scope'
down_revision: Union[str, None] = '012_issue_goals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The old schema had UNIQUE INDEX ix_sync_state_entity_name (from
    # column-level unique=True). Drop it first so we can rebuild with a
    # composite unique on (entity_name, scope).
    op.drop_index('ix_sync_state_entity_name', table_name='sync_state')

    with op.batch_alter_table('sync_state', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('scope', sa.String(255), nullable=False, server_default='')
        )
        batch_op.create_unique_constraint(
            'uq_sync_state_entity_scope', ['entity_name', 'scope']
        )
        batch_op.create_index('ix_sync_state_entity_name', ['entity_name'])
        batch_op.create_index('ix_sync_state_scope', ['scope'])


def downgrade() -> None:
    with op.batch_alter_table('sync_state', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_state_scope')
        batch_op.drop_index('ix_sync_state_entity_name')
        batch_op.drop_constraint('uq_sync_state_entity_scope', type_='unique')
        batch_op.drop_column('scope')

    # Recreate the legacy UNIQUE INDEX on entity_name so the schema matches
    # the pre-013 state exactly.
    op.create_index(
        'ix_sync_state_entity_name', 'sync_state', ['entity_name'], unique=True
    )
