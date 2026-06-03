"""plan_audit journal

Revision ID: 059_plan_audit
Revises: 058_plan_hours_versioning
Create Date: 2026-06-03
"""
from typing import Union
import sqlalchemy as sa
from alembic import op

revision: str = "059_plan_audit"
down_revision: Union[str, None] = "058_plan_hours_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plan_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("issue_id", sa.String(36), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),  # analyst|dev|qa|opo
        sa.Column("value_before", sa.Float(), nullable=True),
        sa.Column("value_after", sa.Float(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),  # jira_sync | manual_edit | manual_revert | jira_sync_conflict | conflict_accepted | conflict_ignored
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plan_audit_issue_created", "plan_audit", ["issue_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_plan_audit_issue_created", table_name="plan_audit")
    op.drop_table("plan_audit")
