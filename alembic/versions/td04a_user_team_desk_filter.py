"""team desk: per-user filter (teams + developers)

Revision ID: td04a_user_team_desk_filter
Revises: td03a_aurora_only_themes
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td04a_user_team_desk_filter"
down_revision: Union[str, None] = "td03a_aurora_only_themes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "team_desk_filter",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("team_desk_filter")
