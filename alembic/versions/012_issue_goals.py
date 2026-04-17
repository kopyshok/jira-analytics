"""add issue.goals + seed jira_goals_field_id

Revision ID: 012_issue_goals
Revises: 011_issue_status_category
Create Date: 2026-04-17

"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '012_issue_goals'
down_revision: Union[str, None] = '011_issue_status_category'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('goals', sa.String(255), nullable=True))

    # Pre-seed AppSetting so sync подтягивает значение сразу.
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT 1 FROM app_settings WHERE key = 'jira_goals_field_id'"
    )).scalar()
    if not exists:
        now = datetime.utcnow().isoformat()
        bind.execute(sa.text(
            "INSERT INTO app_settings (id, key, value, created_at, updated_at) "
            "VALUES (:id, 'jira_goals_field_id', 'customfield_11421', :now, :now)"
        ), {"id": str(uuid.uuid4()), "now": now})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM app_settings WHERE key = 'jira_goals_field_id'"))
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_column('goals')
