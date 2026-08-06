"""kpi: окружение, подтип, тип затрат, cycle time, направление из Jira

Revision ID: k03a_kpi_issue_custom_fields
Revises: k02a_kpi_issue_resolution
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k03a_kpi_issue_custom_fields"
down_revision: Union[str, None] = "k02a_kpi_issue_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("issues") as batch:
        batch.add_column(sa.Column("environment", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("subtype", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("cost_type", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("cycle_time_fact", sa.Float(), nullable=True))
        batch.add_column(sa.Column("direction", sa.String(length=200), nullable=True))
    op.create_index("ix_issues_environment", "issues", ["environment"])
    op.create_index("ix_issues_subtype", "issues", ["subtype"])
    op.create_index("ix_issues_cost_type", "issues", ["cost_type"])
    op.create_index("ix_issues_direction", "issues", ["direction"])


def downgrade() -> None:
    op.drop_index("ix_issues_direction", table_name="issues")
    op.drop_index("ix_issues_cost_type", table_name="issues")
    op.drop_index("ix_issues_subtype", table_name="issues")
    op.drop_index("ix_issues_environment", table_name="issues")
    with op.batch_alter_table("issues") as batch:
        batch.drop_column("direction")
        batch.drop_column("cycle_time_fact")
        batch.drop_column("cost_type")
        batch.drop_column("subtype")
        batch.drop_column("environment")
