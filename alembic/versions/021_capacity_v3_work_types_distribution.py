"""Capacity v3 — absence_reasons directory + Absence.reason_id + Category.work_type_id.

Revision ID: 021_capacity_v3
Revises: 020_capacity_rules_v2
Create Date: 2026-04-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "021_capacity_v3"
down_revision: Union[str, None] = "020_capacity_rules_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_REASONS = [
    # (id, code, label, is_planned, color, sort_order)
    ("reason-vacation", "vacation", "Отпуск", True, "#fa8c16", 0),
    ("reason-sick", "sick", "Больничный", False, "#f5222d", 1),
    ("reason-day_off", "day_off", "Отгул", False, "#1677ff", 2),
    ("reason-other", "other", "Прочее", False, "#8c8c8c", 3),
]


def upgrade() -> None:
    # 1. Create absence_reasons table.
    op.create_table(
        "absence_reasons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_planned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False,
                 server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime, nullable=False,
                 server_default=sa.func.current_timestamp()),
    )

    # 2. Seed default reasons.
    reasons_table = sa.table(
        "absence_reasons",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("is_planned", sa.Boolean),
        sa.column("color", sa.String),
        sa.column("sort_order", sa.Integer),
    )
    op.bulk_insert(reasons_table, [
        {
            "id": rid, "code": code, "label": label,
            "is_planned": is_planned, "color": color, "sort_order": sort_order,
        }
        for rid, code, label, is_planned, color, sort_order in SEED_REASONS
    ])

    # 3. Add absences.reason_id as nullable; backfill from absences.reason.
    with op.batch_alter_table("absences") as batch_op:
        batch_op.add_column(sa.Column("reason_id", sa.String(36), nullable=True))

    # Populate reason_id by matching absences.reason string to absence_reasons.code.
    op.execute("""
        UPDATE absences
        SET reason_id = (
            SELECT id FROM absence_reasons WHERE code = absences.reason
        )
        WHERE reason IS NOT NULL
    """)
    # Fallback for unexpected values.
    op.execute("""
        UPDATE absences
        SET reason_id = 'reason-other'
        WHERE reason_id IS NULL
    """)

    # 4. Make reason_id NOT NULL + FK, drop old reason column.
    with op.batch_alter_table("absences") as batch_op:
        batch_op.alter_column("reason_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_absences_reason_id_absence_reasons",
            "absence_reasons",
            ["reason_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_absences_reason_id", ["reason_id"], unique=False,
        )
        batch_op.drop_column("reason")

    # 5. Add categories.work_type_id (nullable FK).
    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(sa.Column("work_type_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_categories_work_type_id_mandatory_work_types",
            "mandatory_work_types",
            ["work_type_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_categories_work_type_id", ["work_type_id"], unique=False,
        )


def downgrade() -> None:
    # Reverse order.
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_index("ix_categories_work_type_id")
        batch_op.drop_constraint(
            "fk_categories_work_type_id_mandatory_work_types", type_="foreignkey",
        )
        batch_op.drop_column("work_type_id")

    # Restore absences.reason before dropping reason_id (to preserve data).
    with op.batch_alter_table("absences") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reason",
                sa.String(32),
                nullable=False,
                server_default="vacation",
            )
        )

    op.execute("""
        UPDATE absences
        SET reason = (
            SELECT code FROM absence_reasons WHERE id = absences.reason_id
        )
    """)

    with op.batch_alter_table("absences") as batch_op:
        batch_op.drop_index("ix_absences_reason_id")
        batch_op.drop_constraint(
            "fk_absences_reason_id_absence_reasons", type_="foreignkey",
        )
        batch_op.drop_column("reason_id")

    op.drop_table("absence_reasons")
