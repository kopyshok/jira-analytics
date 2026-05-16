"""add_plan_fork_fields

Revision ID: 6a85a18f6971
Revises: d9ef5e667679
Create Date: 2026-05-03 23:30:43.902736

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a85a18f6971"
down_revision: Union[str, None] = "d9ef5e667679"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plans") as batch:
        batch.add_column(sa.Column("parent_plan_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column(
                "is_baseline",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("label", sa.String(255), nullable=True))
        batch.create_foreign_key(
            "fk_resource_plans_parent_plan_id",
            "resource_plans",
            ["parent_plan_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_resource_plans_parent_plan_id", ["parent_plan_id"])


def downgrade() -> None:
    with op.batch_alter_table("resource_plans") as batch:
        batch.drop_index("ix_resource_plans_parent_plan_id")
        batch.drop_constraint("fk_resource_plans_parent_plan_id", type_="foreignkey")
        batch.drop_column("label")
        batch.drop_column("is_baseline")
        batch.drop_column("parent_plan_id")
