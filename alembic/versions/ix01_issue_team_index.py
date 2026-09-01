"""index on issues.team — фильтр команды используется почти на каждом экране

Revision ID: ix01_issue_team_index
Revises: hr01_rule_require_parent
Create Date: 2026-09-01
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'ix01_issue_team_index'
down_revision: Union[str, None] = 'hr01_rule_require_parent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_issues_team', 'issues', ['team'])


def downgrade() -> None:
    op.drop_index('ix_issues_team', table_name='issues')
