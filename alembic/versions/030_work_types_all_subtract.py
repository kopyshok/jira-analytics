"""Set subtracts_from_pool=True for all mandatory work types.

Migration 026 had set subtracts_from_pool=0 for work types that had
categories pointing at them, making them purely informational. Per
user requirement all mandatory work types should deduct from the
planning pool, so we reset all records to True.
"""
from alembic import op

revision = "030_work_types_all_subtract"
down_revision = "a464aa4a0ea1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE mandatory_work_types SET subtracts_from_pool = 1")


def downgrade():
    # Restore the original 026 logic: work types with linked categories → False
    op.execute("""
        UPDATE mandatory_work_types
        SET subtracts_from_pool = 0
        WHERE id IN (
            SELECT DISTINCT work_type_id FROM categories WHERE work_type_id IS NOT NULL
        )
    """)
