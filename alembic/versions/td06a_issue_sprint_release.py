"""team desk: sprint and release fields on issues

Revision ID: td06a_issue_sprint_release
Revises: ix01_issue_team_index
Create Date: 2026-09-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td06a_issue_sprint_release"
down_revision: Union[str, None] = "ix01_issue_team_index"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("sprint", sa.String(255), nullable=True))
        batch.add_column(sa.Column("sprints", sa.Text(), nullable=True))
        batch.add_column(sa.Column("release", sa.String(255), nullable=True))
    op.create_index("ix_issues_sprint", "issues", ["sprint"])
    op.create_index("ix_issues_release", "issues", ["release"])


def downgrade() -> None:
    op.drop_index("ix_issues_release", table_name="issues")
    op.drop_index("ix_issues_sprint", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("release")
        batch.drop_column("sprints")
        batch.drop_column("sprint")
