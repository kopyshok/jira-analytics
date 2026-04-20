"""ScenarioAllocation.involvement_coefficient — reserved for future Gantt planning."""
from alembic import op
import sqlalchemy as sa

revision = "028_allocation_involvement"
down_revision = "027_scenario_team_rules_qa"


def upgrade():
    with op.batch_alter_table("scenario_allocations") as batch:
        batch.add_column(sa.Column("involvement_coefficient", sa.Float, nullable=True))


def downgrade():
    with op.batch_alter_table("scenario_allocations") as batch:
        batch.drop_column("involvement_coefficient")
