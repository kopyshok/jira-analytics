"""Work type subtract_from_pool toggle."""
from alembic import op
import sqlalchemy as sa

revision = "026_work_type_subtract_toggle"
down_revision = "025_role_registry"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("mandatory_work_types") as batch:
        batch.add_column(sa.Column("subtracts_from_pool", sa.Boolean,
                                   nullable=False, server_default=sa.true()))
    # Pre-fill: work types that have at least one Category pointing at them
    # are already accounted for via category-based fact grouping → flip to False.
    op.execute("""
        UPDATE mandatory_work_types
        SET subtracts_from_pool = false
        WHERE id IN (SELECT DISTINCT work_type_id FROM categories WHERE work_type_id IS NOT NULL)
    """)


def downgrade():
    with op.batch_alter_table("mandatory_work_types") as batch:
        batch.drop_column("subtracts_from_pool")
