"""work type is_system flag + other_foreign seed

Revision ID: 044_work_type_is_system
Revises: 043
Create Date: 2026-05-01

"""
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op


revision = "044_work_type_is_system"
down_revision = "043"
branch_labels = None
depends_on = None


SYSTEM_CODES_EXISTING = [
    "organizational",
    "management_admin",
    "support_consult",
    "tech_debt",
    "technical_tasks",
    "project",
]


def upgrade() -> None:
    with op.batch_alter_table("mandatory_work_types") as batch:
        batch.add_column(
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    work_types = sa.table(
        "mandatory_work_types",
        sa.column("id", sa.String),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("subtracts_from_pool", sa.Boolean),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )

    op.execute(
        sa.update(work_types)
        .where(work_types.c.code.in_(SYSTEM_CODES_EXISTING))
        .values(is_system=True)
    )

    now = datetime.utcnow()
    bind = op.get_bind()
    exists = bind.execute(
        sa.select(work_types.c.id).where(work_types.c.code == "other_foreign")
    ).first()
    if not exists:
        bind.execute(
            sa.insert(work_types).values(
                id=str(uuid.uuid4()),
                code="other_foreign",
                label="Прочие / Чужие задачи",
                is_active=True,
                sort_order=99,
                subtracts_from_pool=False,
                is_system=True,
                created_at=now,
                updated_at=now,
            )
        )


def downgrade() -> None:
    work_types = sa.table(
        "mandatory_work_types",
        sa.column("code", sa.String),
    )
    op.execute(sa.delete(work_types).where(work_types.c.code == "other_foreign"))
    with op.batch_alter_table("mandatory_work_types") as batch:
        batch.drop_column("is_system")
