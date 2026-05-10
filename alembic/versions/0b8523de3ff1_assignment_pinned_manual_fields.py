"""assignment pinned/manual fields

Revision ID: 0b8523de3ff1
Revises: 1c9c0b93ba19
Create Date: 2026-05-10 19:17:29.601288

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b8523de3ff1'
down_revision: Union[str, None] = '1c9c0b93ba19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch:
        batch.add_column(sa.Column("pinned_employee", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("pinned_start", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("pinned_split", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("manual_edit_at", sa.DateTime(), nullable=True))
        batch.create_index("ix_resource_plan_assignments_pinned_employee", ["pinned_employee"])
    # Copy data: existing is_pinned → pinned_employee
    op.execute("UPDATE resource_plan_assignments SET pinned_employee = is_pinned")
    with op.batch_alter_table("resource_plan_assignments") as batch:
        batch.drop_index("ix_resource_plan_assignments_is_pinned")
        batch.drop_column("is_pinned")


def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch:
        batch.add_column(sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="0"))
        batch.create_index("ix_resource_plan_assignments_is_pinned", ["is_pinned"])
    op.execute("UPDATE resource_plan_assignments SET is_pinned = pinned_employee")
    with op.batch_alter_table("resource_plan_assignments") as batch:
        batch.drop_index("ix_resource_plan_assignments_pinned_employee")
        batch.drop_column("pinned_employee")
        batch.drop_column("pinned_start")
        batch.drop_column("pinned_split")
        batch.drop_column("manual_edit_at")
