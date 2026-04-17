"""add archive and initiatives_rfa categories

Revision ID: 008_archive_rfa_categories
Revises: 4669ffaff6ba
Create Date: 2026-04-17

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = '008_archive_rfa_categories'
down_revision: Union[str, None] = '4669ffaff6ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


NEW_CATEGORIES = [
    ("archive", "Архив", "#7a7a7a", 20, False),
    ("initiatives_rfa", "Инициативы и RFA", "#ad6fff", 21, False),
]


def upgrade() -> None:
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
        for code, label, color, order, is_sys in NEW_CATEGORIES
    ])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM categories WHERE code IN ('archive', 'initiatives_rfa')"))
