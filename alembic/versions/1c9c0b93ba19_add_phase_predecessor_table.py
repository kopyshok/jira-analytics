"""add phase_predecessor table

Revision ID: 1c9c0b93ba19
Revises: 1b2c3d4e5f60
Create Date: 2026-05-10 19:09:36.736127

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c9c0b93ba19'
down_revision: Union[str, None] = '1b2c3d4e5f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'phase_predecessor',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('successor_assignment_id', sa.String(length=36), nullable=False),
        sa.Column('predecessor_assignment_id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['predecessor_assignment_id'], ['resource_plan_assignments.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['successor_assignment_id'], ['resource_plan_assignments.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'successor_assignment_id',
            'predecessor_assignment_id',
            name='uq_phase_predecessor_pair',
        ),
    )
    with op.batch_alter_table('phase_predecessor', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_phase_predecessor_predecessor_assignment_id'),
            ['predecessor_assignment_id'],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_phase_predecessor_successor_assignment_id'),
            ['successor_assignment_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('phase_predecessor', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_phase_predecessor_successor_assignment_id'))
        batch_op.drop_index(batch_op.f('ix_phase_predecessor_predecessor_assignment_id'))
    op.drop_table('phase_predecessor')
