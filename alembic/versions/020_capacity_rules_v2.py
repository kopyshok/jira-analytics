"""capacity rules v2: mandatory_work_types + role_capacity_rules + employee_capacity_overrides

Clean-start miграция — drop старой monthly_capacity_rules, создаём 3 новых
таблицы и засеиваем 5 базовых типов обязательных работ.

Revision ID: 020_capacity_rules_v2
Revises: 019_employee_teams_and_out_of_scope
Create Date: 2026-04-19
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = '020_capacity_rules_v2'
down_revision: Union[str, None] = '019_employee_teams_and_out_of_scope'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_WORK_TYPES = [
    # (code, label, sort_order)
    ("organizational", "Организационные вопросы", 0),
    ("management_admin", "Руководство и администрирование", 1),
    ("support_consult", "Сопровождение и консультация", 2),
    ("tech_debt", "Технический долг", 3),
    ("technical_tasks", "Технические задачи", 4),
]


def upgrade() -> None:
    # 1. Drop old flat rules table.
    op.drop_table("monthly_capacity_rules")

    # 2. Mandatory work type directory.
    op.create_table(
        "mandatory_work_types",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("code", name="uq_mandatory_work_types_code"),
    )

    # 3. Role × quarter × work_type rules (role=NULL = fallback "для всех").
    op.create_table(
        "role_capacity_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column(
            "work_type_id", sa.String(length=36),
            sa.ForeignKey("mandatory_work_types.id"), nullable=False,
        ),
        sa.Column("percent_of_norm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "year", "quarter", "role", "work_type_id",
            name="uq_role_capacity_rule_scope",
        ),
    )

    # 4. Per-employee overrides (priority > role rule).
    op.create_table(
        "employee_capacity_overrides",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column(
            "employee_id", sa.String(length=36),
            sa.ForeignKey("employees.id"), nullable=False, index=True,
        ),
        sa.Column(
            "work_type_id", sa.String(length=36),
            sa.ForeignKey("mandatory_work_types.id"), nullable=False,
        ),
        sa.Column("percent_of_norm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "year", "quarter", "employee_id", "work_type_id",
            name="uq_employee_capacity_override_scope",
        ),
    )

    # 5. Seed 5 базовых типов обязательных работ.
    now = datetime.utcnow().replace(microsecond=0)
    op.bulk_insert(
        sa.table(
            "mandatory_work_types",
            sa.column("id", sa.String),
            sa.column("code", sa.String),
            sa.column("label", sa.String),
            sa.column("is_active", sa.Boolean),
            sa.column("sort_order", sa.Integer),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                "id": str(uuid.uuid4()),
                "code": code, "label": label, "is_active": True,
                "sort_order": order, "created_at": now, "updated_at": now,
            }
            for code, label, order in SEED_WORK_TYPES
        ],
    )


def downgrade() -> None:
    op.drop_table("employee_capacity_overrides")
    op.drop_table("role_capacity_rules")
    op.drop_table("mandatory_work_types")

    op.create_table(
        "monthly_capacity_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("percent_of_norm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
