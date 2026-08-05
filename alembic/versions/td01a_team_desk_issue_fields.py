"""team desk: developer + dev est fields on issues

Revision ID: td01a_team_desk_issue_fields
Revises: k15a_kpi_issue_paused_days
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td01a_team_desk_issue_fields"
down_revision: Union[str, None] = "k15a_kpi_issue_paused_days"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("developer_account_id", sa.String(128), nullable=True))
        batch.add_column(sa.Column("developer_display_name", sa.String(255), nullable=True))
        batch.add_column(sa.Column("dev_est_hours", sa.Float(), nullable=True))
    op.create_index("ix_issues_developer_account_id", "issues", ["developer_account_id"])


def downgrade() -> None:
    op.drop_index("ix_issues_developer_account_id", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("dev_est_hours")
        batch.drop_column("developer_display_name")
        batch.drop_column("developer_account_id")
