"""add predecessors_user_set to resource_plan_assignments

Revision ID: b6537be9bb81
Revises: 1b0ee1f72ceb
Create Date: 2026-05-19 13:56:10.002973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6537be9bb81'
down_revision: Union[str, None] = '1b0ee1f72ceb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "predecessors_user_set",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.drop_column("predecessors_user_set")
