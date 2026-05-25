"""feedback items

Revision ID: 052_feedback_items
Revises: 871f7c1d03ab
Create Date: 2026-05-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "052_feedback_items"
down_revision: Union[str, None] = "871f7c1d03ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_items",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("page_url", sa.String(2048), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.Column("read_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("steps_to_reproduce", sa.Text(), nullable=True),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("actual", sa.Text(), nullable=True),
        sa.Column("context_json", sa.Text(), nullable=True),
        sa.Column("attachments_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedback_items_author_id", "feedback_items", ["author_id"])
    op.create_index(
        "ix_feedback_kind_read_created",
        "feedback_items",
        ["kind", "read_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_feedback_kind_read_created", table_name="feedback_items")
    op.drop_index("ix_feedback_items_author_id", table_name="feedback_items")
    op.drop_table("feedback_items")
