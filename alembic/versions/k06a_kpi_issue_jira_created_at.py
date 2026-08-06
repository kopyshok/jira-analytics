"""kpi: дата создания задачи в Jira

Revision ID: k06a_kpi_issue_jira_created_at
Revises: k05a_kpi_dictionaries
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k06a_kpi_issue_jira_created_at"
down_revision: Union[str, None] = "k05a_kpi_dictionaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("jira_created_at", sa.DateTime(), nullable=True))
    op.create_index("ix_issues_jira_created_at", "issues", ["jira_created_at"])


def downgrade() -> None:
    op.drop_index("ix_issues_jira_created_at", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("jira_created_at")
