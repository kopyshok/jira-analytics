"""Backfill: задачи в статусе 'Отменено' без assigned_category → архив.

Revision ID: 055_autoarchive_cancelled
Revises: 054_lowercase_emails
Create Date: 2026-06-01

PM не нужны Отменено-задачи в стеке разбора. Все будущие синки sync_issues
проставляют archive автоматически (см. _upsert_issue). Этот backfill
переводит уже накопившиеся Отменено-задачи без assigned_category.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "055_autoarchive_cancelled"
down_revision: Union[str, None] = "054_lowercase_emails"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    issues = sa.table(
        "issues",
        sa.column("status", sa.String),
        sa.column("assigned_category", sa.String),
        sa.column("category", sa.String),
        sa.column("include_in_analysis", sa.Boolean),
        sa.column("category_verified", sa.Boolean),
    )
    op.execute(
        sa.update(issues)
        .where(issues.c.status == "Отменено")
        .where(issues.c.assigned_category.is_(None))
        .values(
            assigned_category="archive",
            category="archive",
            include_in_analysis=False,
            category_verified=True,
        )
    )


def downgrade() -> None:
    pass
