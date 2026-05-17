"""add assignment out_of_quarter and daily_hours

Revision ID: ecc63631fea1
Revises: 0426e0dd23cc
Create Date: 2026-05-17 21:05:53.308792

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ecc63631fea1'
down_revision: Union[str, None] = '0426e0dd23cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "out_of_quarter",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(
            sa.Column("daily_hours_json", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch_op:
        batch_op.drop_column("daily_hours_json")
        batch_op.drop_column("out_of_quarter")
