"""Add categories table with default data

Revision ID: 006_categories
Revises: 005_app_settings
Create Date: 2026-04-16

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = '006_categories'
down_revision: Union[str, None] = '005_app_settings'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_CATEGORIES = [
    ("support_consultation", "Сопровождение и консультация", "#378ADD", 1, False),
    ("quarterly_tasks", "Квартальные задачи", "#1D9E75", 2, False),
    ("team_meetings", "Встречи продуктовых команд и рабочих групп", "#EF9F27", 3, False),
    ("internal_communications", "Внутренние коммуникации команд", "#7F77DD", 4, False),
    ("tech_debt", "Технический долг", "#00c9c8", 5, False),
    ("pm_management", "PM управление", "#f5c842", 6, False),
    ("unfilled_worklog", "Незаполненные / сомнительные worklog", "#888780", 99, True),
]


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('code', sa.String(100), nullable=False, unique=True, index=True),
        sa.Column('label', sa.String(255), nullable=False),
        sa.Column('color', sa.String(7), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    categories_table = sa.table(
        'categories',
        sa.column('id', sa.String),
        sa.column('code', sa.String),
        sa.column('label', sa.String),
        sa.column('color', sa.String),
        sa.column('sort_order', sa.Integer),
        sa.column('is_system', sa.Boolean),
    )
    op.bulk_insert(categories_table, [
        {
            "id": str(uuid.uuid4()),
            "code": code,
            "label": label,
            "color": color,
            "sort_order": order,
            "is_system": is_sys,
        }
        for code, label, color, order, is_sys in DEFAULT_CATEGORIES
    ])


def downgrade() -> None:
    op.drop_table('categories')
