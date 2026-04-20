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

    op.create_table(
        "scenario_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("planning_scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("work_type_id", sa.String(36),
                  sa.ForeignKey("mandatory_work_types.id"), nullable=False),
        sa.Column("percent_of_norm", sa.Float, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("scenario_id", "role", "work_type_id",
                            name="uq_scenario_rule_scope"),
    )


def downgrade():
    op.drop_table("scenario_rules", if_exists=True)

    with op.batch_alter_table("planning_scenarios") as batch:
        batch.drop_column("external_qa_hours")
        batch.drop_column("team")
