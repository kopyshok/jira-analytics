"""backlog_items.archived_at — explicit archive lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = "029_backlog_archived_at"
down_revision = "028_allocation_involvement"


def upgrade():
    with op.batch_alter_table("backlog_items") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_column("archived_at")
