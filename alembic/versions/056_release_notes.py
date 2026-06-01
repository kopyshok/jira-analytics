"""release_notes + user.last_seen_release_version

Revision ID: 056_release_notes
Revises: 055_autoarchive_cancelled
Create Date: 2026-06-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "056_release_notes"
down_revision: Union[str, None] = "055_autoarchive_cancelled"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "release_notes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version", sa.String(length=32), nullable=True),
        sa.Column("note_type", sa.String(length=20), nullable=False),
        sa.Column("section", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("help_link", sa.String(length=255), nullable=True),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_release_notes_version", "release_notes", ["version"])
    op.create_index("ix_release_notes_version_type", "release_notes", ["version", "note_type"])

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("last_seen_release_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_seen_release_version")
    op.drop_index("ix_release_notes_version_type", table_name="release_notes")
    op.drop_index("ix_release_notes_version", table_name="release_notes")
    op.drop_table("release_notes")
