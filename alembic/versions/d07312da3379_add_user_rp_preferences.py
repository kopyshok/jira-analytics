"""add user_rp_preferences

Revision ID: d07312da3379
Revises: eff9e06ce1f5
Create Date: 2026-05-10 19:47:03.642825

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd07312da3379'
down_revision: Union[str, None] = 'eff9e06ce1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_rp_preferences",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "hide_weekends",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "collapsed_initiative_ids",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("view_mode", sa.String(10), nullable=True),
        sa.Column(
            "show_relay",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_rp_preferences")
