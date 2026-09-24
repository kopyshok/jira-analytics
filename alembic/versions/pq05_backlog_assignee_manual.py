"""backlog_items: исполнитель, выбранный в сценарии вручную

Revision ID: pq05_backlog_assignee_manual
Revises: pq03_issue_plan_sources
Create Date: 2026-09-24

Самодостаточна: не импортирует код приложения.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pq05_backlog_assignee_manual"
down_revision: Union[str, None] = "pq03_issue_plan_sources"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(
            sa.Column("assignee_manual", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("assignee_jira_account_at_choice", sa.String(length=128), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("assignee_jira_account_at_choice")
        batch.drop_column("assignee_manual")
