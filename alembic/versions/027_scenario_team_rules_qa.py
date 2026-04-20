"""Scenario gains team/external_qa_hours + per-scenario rules table."""
from alembic import op
import sqlalchemy as sa

revision = "027_scenario_team_rules_qa"
down_revision = "026_work_type_subtract_toggle"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("planning_scenarios") as batch:
        batch.add_column(sa.Column("team", sa.String(100), nullable=True))
        batch.add_column(sa.Column("external_qa_hours", sa.Float, nullable=True))


def downgrade():
    with op.batch_alter_table("planning_scenarios") as batch:
        batch.drop_column("external_qa_hours")
        batch.drop_column("team")
