"""Add analytics fields to models

Revision ID: 002_analytics_fields
Revises: 001_initial
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002_analytics_fields'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add role/team/department to employees
    with op.batch_alter_table('employees') as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('team', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('department', sa.String(100), nullable=True))
    
    # Add category/estimated_hours to issues
    with op.batch_alter_table('issues') as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(50), nullable=True))
        batch_op.add_column(sa.Column('estimated_hours', sa.Float(), nullable=True))
    
    # Add is_active to projects
    with op.batch_alter_table('projects') as batch_op:
        batch_op.add_column(sa.Column('is_active', sa.Boolean(), server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('projects') as batch_op:
        batch_op.drop_column('is_active')
    
    with op.batch_alter_table('issues') as batch_op:
        batch_op.drop_column('estimated_hours')
        batch_op.drop_column('category')
    
    with op.batch_alter_table('employees') as batch_op:
        batch_op.drop_column('department')
        batch_op.drop_column('team')
        batch_op.drop_column('role')
