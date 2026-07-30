"""kpi: дата внесения записи о трудозатратах

Revision ID: k01a_kpi_worklog_created
Revises: f4b2c8d1e7a3
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k01a_kpi_worklog_created"
down_revision: Union[str, None] = "f4b2c8d1e7a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("worklogs") as batch:
        batch.add_column(sa.Column("jira_created_at", sa.DateTime(), nullable=True))
    op.create_index("ix_worklogs_jira_created_at", "worklogs", ["jira_created_at"])


def downgrade() -> None:
    op.drop_index("ix_worklogs_jira_created_at", table_name="worklogs")
    with op.batch_alter_table("worklogs") as batch:
        batch.drop_column("jira_created_at")
