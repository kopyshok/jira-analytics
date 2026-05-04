"""resource_plan_assignment is_pinned

Revision ID: 7f9c9e09d8bd
Revises: 6a85a18f6971
Create Date: 2026-05-04 08:03:32.222334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f9c9e09d8bd'
down_revision: Union[str, None] = '6a85a18f6971'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.add_column(
            sa.Column("is_pinned", sa.Boolean(), server_default="0", nullable=False)
        )
        batch_op.create_index(
            "ix_resource_plan_assignments_is_pinned",
            ["is_pinned"],
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.drop_index("ix_resource_plan_assignments_is_pinned")
        batch_op.drop_column("is_pinned")
