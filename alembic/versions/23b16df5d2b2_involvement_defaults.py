"""involvement_defaults

Revision ID: 23b16df5d2b2
Revises: ce7f3e3e1aa5
Create Date: 2026-06-18 23:21:13.106187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '23b16df5d2b2'
down_revision: Union[str, None] = 'ce7f3e3e1aa5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "involvement_defaults",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("team", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("effective_year", sa.Integer(), nullable=False),
        sa.Column("effective_quarter", sa.Integer(), nullable=False),
        sa.Column("involvement", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team", "role", "effective_year", "effective_quarter",
            name="uq_involvement_default_scope",
        ),
    )
    op.create_index(
        "ix_involvement_defaults_team", "involvement_defaults", ["team"],
    )


def downgrade() -> None:
    op.drop_index("ix_involvement_defaults_team", table_name="involvement_defaults")
    op.drop_table("involvement_defaults")
