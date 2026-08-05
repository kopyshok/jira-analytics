"""team desk: reviewed marks

Revision ID: td02a_team_desk_marks
Revises: td01a_team_desk_issue_fields
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td02a_team_desk_marks"
down_revision: Union[str, None] = "td01a_team_desk_issue_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_desk_marks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "issue_id",
            sa.String(36),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("flag", sa.String(32), nullable=False),
        sa.Column("signature", sa.String(160), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("marked_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("issue_id", "flag", name="uq_team_desk_mark"),
    )
    op.create_index("ix_team_desk_marks_issue_id", "team_desk_marks", ["issue_id"])


def downgrade() -> None:
    op.drop_index("ix_team_desk_marks_issue_id", table_name="team_desk_marks")
    op.drop_table("team_desk_marks")
