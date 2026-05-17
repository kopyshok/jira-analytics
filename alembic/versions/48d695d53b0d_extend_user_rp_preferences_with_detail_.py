"""extend user_rp_preferences with detail sections sliders pulses

Revision ID: 48d695d53b0d
Revises: ecc63631fea1
Create Date: 2026-05-17 21:37:21.182927

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48d695d53b0d'
down_revision: Union[str, None] = 'ecc63631fea1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user_rp_preferences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "detail_sections_visible",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column(
                "detail_sections_collapsed",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.add_column(
            sa.Column(
                "fill_intensity_pct",
                sa.Integer(),
                nullable=False,
                server_default="50",
            )
        )
        batch_op.add_column(
            sa.Column(
                "fill_contrast_pct",
                sa.Integer(),
                nullable=False,
                server_default="50",
            )
        )
        batch_op.add_column(
            sa.Column(
                "pulse_highlighted_employee",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "pulse_critical_path",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.add_column(
            sa.Column(
                "out_of_quarter_months",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column(
                "hide_weekend_stripes_week_mode",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("user_rp_preferences") as batch_op:
        batch_op.drop_column("hide_weekend_stripes_week_mode")
        batch_op.drop_column("out_of_quarter_months")
        batch_op.drop_column("pulse_critical_path")
        batch_op.drop_column("pulse_highlighted_employee")
        batch_op.drop_column("fill_contrast_pct")
        batch_op.drop_column("fill_intensity_pct")
        batch_op.drop_column("detail_sections_collapsed")
        batch_op.drop_column("detail_sections_visible")
