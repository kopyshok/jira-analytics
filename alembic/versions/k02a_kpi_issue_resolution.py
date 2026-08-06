"""kpi: резолюция и дата резолюции задачи

Revision ID: k02a_kpi_issue_resolution
Revises: k01a_kpi_worklog_created
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k02a_kpi_issue_resolution"
down_revision: Union[str, None] = "k01a_kpi_worklog_created"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("resolution", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.create_index("ix_issues_resolution", "issues", ["resolution"])
    op.create_index("ix_issues_resolved_at", "issues", ["resolved_at"])


def downgrade() -> None:
    op.drop_index("ix_issues_resolved_at", table_name="issues")
    op.drop_index("ix_issues_resolution", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("resolved_at")
        batch.drop_column("resolution")
