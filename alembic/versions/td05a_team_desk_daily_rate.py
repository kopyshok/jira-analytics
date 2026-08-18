"""team desk: daily rate for long-running issues

Revision ID: td05a_team_desk_daily_rate
Revises: k16a_kpi_metric_empty_policy
Create Date: 2026-08-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td05a_team_desk_daily_rate"
down_revision: Union[str, None] = "k16a_kpi_metric_empty_policy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_desk_daily_rates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "issue_id",
            sa.String(36),
            sa.ForeignKey("issues.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column(
            "created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("issue_id", name="uq_team_desk_daily_rate"),
    )
    op.create_index(
        "ix_team_desk_daily_rates_issue_id", "team_desk_daily_rates", ["issue_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_team_desk_daily_rates_issue_id", table_name="team_desk_daily_rates"
    )
    op.drop_table("team_desk_daily_rates")
