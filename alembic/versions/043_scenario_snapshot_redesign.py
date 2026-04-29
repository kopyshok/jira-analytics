"""scenario snapshot redesign

- расширение scenario_revisions: parent_revision_id, approved_by_user_id, algo_version
- расширение scenario_capacity_snapshots: gross_hours, absence_hours, mandatory_hours, project_hours
- расширение scenario_norm_snapshots: is_external
- новые таблицы: scenario_team_snapshots, scenario_calendar_snapshots, scenario_rules_snapshots,
  scenario_allocation_snapshots, scenario_allocation_breakdown_snapshots, scenario_dictionary_snapshots

Revision ID: 043
Revises: 042
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = '043'
down_revision = '042'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- scenario_revisions: новые поля ---
    # Добавляем колонки отдельно от FK, чтобы избежать CircularDependencyError
    # при batch-пересборке таблицы с self-referencing FK (parent_revision_id).
    with op.batch_alter_table("scenario_revisions") as batch_op:
        batch_op.add_column(sa.Column("parent_revision_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("approved_by_user_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("algo_version", sa.String(length=16), nullable=False, server_default="v1"))
    with op.batch_alter_table("scenario_revisions", recreate="always") as batch_op:
        batch_op.create_foreign_key(
            "fk_scenario_revisions_parent",
            "scenario_revisions",
            ["parent_revision_id"], ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_scenario_revisions_user",
            "users",
            ["approved_by_user_id"], ["id"],
            ondelete="SET NULL",
        )

    # --- scenario_capacity_snapshots: новые поля ---
    with op.batch_alter_table("scenario_capacity_snapshots") as batch_op:
        batch_op.add_column(sa.Column("gross_hours", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("absence_hours", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("mandatory_hours", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("project_hours", sa.Float(), nullable=True))

    # --- scenario_norm_snapshots: is_external ---
    with op.batch_alter_table("scenario_norm_snapshots") as batch_op:
        batch_op.add_column(sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.create_unique_constraint(
            "uq_scenario_norm_snap_rev_emp_ym_wt_ext",
            ["revision_id", "employee_id", "year", "month", "work_type_id", "is_external"],
        )

    # --- scenario_team_snapshots ---
    op.create_table(
        "scenario_team_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("hours_per_day", sa.Float(), nullable=False, server_default="8.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_scenario_team_snapshots_revision_role", "scenario_team_snapshots", ["revision_id", "role"])

    # --- scenario_calendar_snapshots ---
    op.create_table(
        "scenario_calendar_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("is_workday", sa.Boolean(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "date", name="uq_scenario_calendar_snap_rev_date"),
    )

    # --- scenario_rules_snapshots ---
    op.create_table(
        "scenario_rules_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role", sa.String(50), nullable=True),
        sa.Column("work_type_id", sa.String(36), nullable=True),
        sa.Column("work_type_label", sa.String(255), nullable=False),
        sa.Column("pct_of_norm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "role", "work_type_id", name="uq_scenario_rules_snap_rev_role_wt"),
    )

    # --- scenario_allocation_snapshots ---
    op.create_table(
        "scenario_allocation_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("allocation_id", sa.String(36), nullable=True),
        sa.Column("backlog_item_id", sa.String(36), nullable=True),
        sa.Column("sort_order", sa.Float(), nullable=True),
        sa.Column("included_flag", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("involvement_coefficient", sa.Float(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issue_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("customer", sa.Text(), nullable=True),
        sa.Column("cost_type", sa.String(50), nullable=True),
        sa.Column("impact", sa.String(20), nullable=True),
        sa.Column("risk", sa.String(20), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("estimate_analyst_hours", sa.Float(), nullable=True),
        sa.Column("estimate_dev_hours", sa.Float(), nullable=True),
        sa.Column("estimate_qa_hours", sa.Float(), nullable=True),
        sa.Column("estimate_opo_hours", sa.Float(), nullable=True),
        sa.Column("opo_analyst_ratio", sa.Float(), nullable=True),
        sa.Column("assignee_employee_id", sa.String(36), nullable=True),
        sa.Column("assignee_role_at_approval", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- scenario_allocation_breakdown_snapshots ---
    op.create_table(
        "scenario_allocation_breakdown_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("allocation_id", sa.String(36), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hours", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "revision_id", "allocation_id", "month", "role", "employee_id", "is_external",
            name="uq_alloc_breakdown_rev_alloc_month_role_emp_ext",
        ),
    )
    op.create_index(
        "ix_alloc_breakdown_rev_alloc_month",
        "scenario_allocation_breakdown_snapshots",
        ["revision_id", "allocation_id", "month"],
    )

    # --- scenario_dictionary_snapshots ---
    op.create_table(
        "scenario_dictionary_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), sa.ForeignKey("scenario_revisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("original_id", sa.String(36), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("extra_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("revision_id", "kind", "original_id", name="uq_scenario_dict_snap_rev_kind_id"),
    )


def downgrade() -> None:
    op.drop_table("scenario_dictionary_snapshots")
    op.drop_index("ix_alloc_breakdown_rev_alloc_month", table_name="scenario_allocation_breakdown_snapshots")
    op.drop_table("scenario_allocation_breakdown_snapshots")
    op.drop_table("scenario_allocation_snapshots")
    op.drop_table("scenario_rules_snapshots")
    op.drop_table("scenario_calendar_snapshots")
    op.drop_index("ix_scenario_team_snapshots_revision_role", table_name="scenario_team_snapshots")
    op.drop_table("scenario_team_snapshots")
    with op.batch_alter_table("scenario_norm_snapshots") as batch_op:
        batch_op.drop_constraint("uq_scenario_norm_snap_rev_emp_ym_wt_ext", type_="unique")
        batch_op.drop_column("is_external")
    with op.batch_alter_table("scenario_capacity_snapshots") as batch_op:
        batch_op.drop_column("project_hours")
        batch_op.drop_column("mandatory_hours")
        batch_op.drop_column("absence_hours")
        batch_op.drop_column("gross_hours")
    # Сначала удаляем FK (recreate, чтобы убрать self-referencing FK), затем колонки.
    with op.batch_alter_table("scenario_revisions", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_scenario_revisions_user", type_="foreignkey")
        batch_op.drop_constraint("fk_scenario_revisions_parent", type_="foreignkey")
    with op.batch_alter_table("scenario_revisions") as batch_op:
        batch_op.drop_column("algo_version")
        batch_op.drop_column("approved_by_user_id")
        batch_op.drop_column("parent_revision_id")
