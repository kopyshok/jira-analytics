"""drop result_flow_json from project_ai_summaries

Revision ID: 049_drop_result_flow_json
Revises: 048_confluence_page_cache
Create Date: 2026-05-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "049_drop_result_flow_json"
down_revision: Union[str, None] = "048_confluence_page_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("project_ai_summaries") as batch_op:
        batch_op.drop_column("result_flow_json")


def downgrade() -> None:
    with op.batch_alter_table("project_ai_summaries") as batch_op:
        batch_op.add_column(
            sa.Column("result_flow_json", sa.Text(), nullable=False, server_default="[]")
        )
