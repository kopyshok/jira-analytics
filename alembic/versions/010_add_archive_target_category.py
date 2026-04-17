"""add archive_target category

Revision ID: 010_archive_target_category
Revises: 009_issue_status_changed_at
Create Date: 2026-04-17

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = '010_archive_target_category'
down_revision: Union[str, None] = '009_issue_status_changed_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    op.bulk_insert(categories_table, [{
        "id": str(uuid.uuid4()),
        "code": "archive_target",
        "label": "Архив целевых задач",
        "color": "#5a5a5a",
        "sort_order": 22,
        "is_system": False,
    }])


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM categories WHERE code = 'archive_target'"))
