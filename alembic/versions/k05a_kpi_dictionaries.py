"""kpi: справочники метрик, профилей, нормативов и утверждений

Revision ID: k05a_kpi_dictionaries
Revises: k04a_kpi_issue_links
Create Date: 2026-07-30
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k05a_kpi_dictionaries"
down_revision: Union[str, None] = "k04a_kpi_issue_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kpi_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("calc_kind", sa.String(length=32), nullable=False),
        sa.Column("numerator_json", sa.Text(), nullable=False),
        sa.Column("denominator_json", sa.Text(), nullable=True),
        sa.Column("fact_field", sa.String(length=64), nullable=True),
        sa.Column("score_fields", sa.Text(), nullable=True),
        sa.Column("score_max", sa.Float(), nullable=True),
        sa.Column("invert", sa.Boolean(), nullable=False),
        sa.Column("cap_at_100", sa.Boolean(), nullable=False),
        sa.Column("is_builtin", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "kpi_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("role_code", sa.String(length=64), nullable=True),
        sa.Column("target_pct", sa.Float(), nullable=False),
        sa.Column("warn_band_pct", sa.Float(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_kpi_profiles_role_code", "kpi_profiles", ["role_code"])

    op.create_table(
        "kpi_profile_metrics",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("profile_id", sa.String(length=36),
                  sa.ForeignKey("kpi_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_id", sa.String(length=36),
                  sa.ForeignKey("kpi_metrics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("profile_id", "metric_id", name="uq_profile_metric"),
    )
    op.create_index("ix_kpi_profile_metrics_profile", "kpi_profile_metrics", ["profile_id"])
    op.create_index("ix_kpi_profile_metrics_metric", "kpi_profile_metrics", ["metric_id"])

    op.create_table(
        "kpi_cycle_time_norms",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("team", sa.String(length=200), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("norm_value", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team", "year", "quarter", name="uq_kpi_ct_norm"),
    )
    op.create_index("ix_kpi_cycle_time_norms_team", "kpi_cycle_time_norms", ["team"])

    op.create_table(
        "kpi_approvals",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("team", sa.String(length=200), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.String(length=255), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("team", "year", "month", name="uq_kpi_approval"),
    )
    op.create_index("ix_kpi_approvals_team", "kpi_approvals", ["team"])


def downgrade() -> None:
    op.drop_table("kpi_approvals")
    op.drop_table("kpi_cycle_time_norms")
    op.drop_table("kpi_profile_metrics")
    op.drop_table("kpi_profiles")
    op.drop_table("kpi_metrics")
