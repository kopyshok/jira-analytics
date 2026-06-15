"""add work_desks table

Рабочий стол аналитика — публичная страница-монитор по токену.

Revision ID: 063_work_desks
Revises: 062_cleanup_draft_allocations_for_approved_included
Create Date: 2026-06-15
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "063_work_desks"
down_revision: Union[str, None] = "062_cleanup_draft_allocations_for_approved_included"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_desks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.String(length=36), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "enabled_widgets", sa.Text(), server_default="[]", nullable=False
        ),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("work_desks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_work_desks_employee_id"), ["employee_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_work_desks_token"), ["token"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("work_desks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_work_desks_token"))
        batch_op.drop_index(batch_op.f("ix_work_desks_employee_id"))
    op.drop_table("work_desks")
