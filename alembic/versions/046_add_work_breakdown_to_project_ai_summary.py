"""add work_breakdown_json to project_ai_summaries

Revision ID: 046_add_work_breakdown_to_project_ai_summary
Revises: 045_user_period_and_analytics_columns
Create Date: 2026-05-02

"""
import sqlalchemy as sa
from alembic import op

revision = "046_add_work_breakdown_to_project_ai_summary"
down_revision = "cc4e80e172fa"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("project_ai_summaries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("work_breakdown_json", sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table("project_ai_summaries", schema=None) as batch_op:
        batch_op.drop_column("work_breakdown_json")
