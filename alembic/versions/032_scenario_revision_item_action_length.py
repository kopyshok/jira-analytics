"""Widen scenario_revision_items.action from String(8) to String(16)."""

from alembic import op
import sqlalchemy as sa

revision = "032_scenario_revision_item_action_length"
down_revision = "031_scenario_revision_history"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("scenario_revision_items") as batch_op:
        batch_op.alter_column("action", type_=sa.String(16), existing_nullable=False)


def downgrade():
    with op.batch_alter_table("scenario_revision_items") as batch_op:
        batch_op.alter_column("action", type_=sa.String(8), existing_nullable=False)
