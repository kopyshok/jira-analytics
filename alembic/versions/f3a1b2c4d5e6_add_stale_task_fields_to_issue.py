"""add stale-task fields to issue (jira_updated_at, reporter/assignee account ids)

Revision ID: f3a1b2c4d5e6
Revises: 23b16df5d2b2
Create Date: 2026-06-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a1b2c4d5e6'
down_revision: Union[str, None] = '23b16df5d2b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.add_column(sa.Column('assignee_account_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('reporter_account_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('reporter_display_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('jira_updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_issues_assignee_account_id', ['assignee_account_id'], unique=False)
        batch_op.create_index('ix_issues_reporter_account_id', ['reporter_account_id'], unique=False)
        batch_op.create_index('ix_issues_jira_updated_at', ['jira_updated_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('issues', schema=None) as batch_op:
        batch_op.drop_index('ix_issues_jira_updated_at')
        batch_op.drop_index('ix_issues_reporter_account_id')
        batch_op.drop_index('ix_issues_assignee_account_id')
        batch_op.drop_column('jira_updated_at')
        batch_op.drop_column('reporter_display_name')
        batch_op.drop_column('reporter_account_id')
        batch_op.drop_column('assignee_account_id')
