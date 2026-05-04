"""add issue.goal_text + issue.current_behavior, seed jira_goal_field_id + jira_current_behavior_field_id

Revision ID: 047_issue_description_extra_fields
Revises: 7f9c9e09d8bd
Create Date: 2026-05-04
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "047_issue_description_extra_fields"
down_revision: Union[str, None] = "7f9c9e09d8bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.add_column(sa.Column("goal_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("current_behavior", sa.Text(), nullable=True))

    bind = op.get_bind()
    now = datetime.utcnow().isoformat()
    for key in ("jira_goal_field_id", "jira_current_behavior_field_id"):
        exists = bind.execute(
            sa.text("SELECT 1 FROM app_settings WHERE key = :k"), {"k": key}
        ).scalar()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO app_settings (id, key, value, created_at, updated_at) "
                    "VALUES (:id, :k, '', :now, :now)"
                ),
                {"id": str(uuid.uuid4()), "k": key, "now": now},
            )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM app_settings WHERE key IN ('jira_goal_field_id', 'jira_current_behavior_field_id')"
    ))
    with op.batch_alter_table("issues", schema=None) as batch_op:
        batch_op.drop_column("current_behavior")
        batch_op.drop_column("goal_text")
