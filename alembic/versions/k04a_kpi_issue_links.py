"""kpi: выгрузка связей задач из Jira

Revision ID: k04a_kpi_issue_links
Revises: k03a_kpi_issue_custom_fields
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k04a_kpi_issue_links"
down_revision: Union[str, None] = "k03a_kpi_issue_custom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issue_links",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_issue_id", sa.String(length=36),
                  sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_issue_id", sa.String(length=36),
                  sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("source_issue_id", "target_issue_id", "link_type",
                            name="uq_issue_link"),
    )
    op.create_index("ix_issue_links_source", "issue_links", ["source_issue_id"])
    op.create_index("ix_issue_links_target", "issue_links", ["target_issue_id"])
    op.create_index("ix_issue_links_type", "issue_links", ["link_type"])


def downgrade() -> None:
    op.drop_table("issue_links")
