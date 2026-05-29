"""scheduled_block multi-role/employee

Revision ID: eff9e06ce1f5
Revises: 0b8523de3ff1
Create Date: 2026-05-10 19:27:44.137023

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "eff9e06ce1f5"
down_revision: Union[str, None] = "0b8523de3ff1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_block_role",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "block_id",
            sa.String(36),
            sa.ForeignKey("scheduled_blocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            sa.String(36),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_scheduled_block_role_block_id",
        "scheduled_block_role",
        ["block_id"],
    )
    op.create_table(
        "scheduled_block_employee",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "block_id",
            sa.String(36),
            sa.ForeignKey("scheduled_blocks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.String(36),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_scheduled_block_employee_block_id",
        "scheduled_block_employee",
        ["block_id"],
    )

    # Data migration — copy existing single role_id / employee_id to new tables.
    bind = op.get_bind()
    role_rows = bind.execute(
        sa.text(
            """
            SELECT id, role_id
            FROM scheduled_blocks
            WHERE role_id IS NOT NULL
            """
        )
    ).all()
    if role_rows:
        scheduled_block_role = sa.table(
            "scheduled_block_role",
            sa.column("id", sa.String),
            sa.column("block_id", sa.String),
            sa.column("role_id", sa.String),
        )
        op.bulk_insert(
            scheduled_block_role,
            [
                {
                    "id": str(uuid.uuid4()),
                    "block_id": block_id,
                    "role_id": role_id,
                }
                for block_id, role_id in role_rows
            ],
        )

    employee_rows = bind.execute(
        sa.text(
            """
            SELECT id, employee_id
            FROM scheduled_blocks
            WHERE employee_id IS NOT NULL
            """
        )
    ).all()
    if employee_rows:
        scheduled_block_employee = sa.table(
            "scheduled_block_employee",
            sa.column("id", sa.String),
            sa.column("block_id", sa.String),
            sa.column("employee_id", sa.String),
        )
        op.bulk_insert(
            scheduled_block_employee,
            [
                {
                    "id": str(uuid.uuid4()),
                    "block_id": block_id,
                    "employee_id": employee_id,
                }
                for block_id, employee_id in employee_rows
            ],
        )

    # Drop legacy columns.
    with op.batch_alter_table("scheduled_blocks") as batch:
        batch.drop_column("role_id")
        batch.drop_column("employee_id")


def downgrade() -> None:
    with op.batch_alter_table("scheduled_blocks") as batch:
        batch.add_column(sa.Column("role_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("employee_id", sa.String(36), nullable=True))

    op.execute(
        """
        UPDATE scheduled_blocks
        SET role_id = (
            SELECT role_id FROM scheduled_block_role
            WHERE block_id = scheduled_blocks.id LIMIT 1
        )
        """
    )
    op.execute(
        """
        UPDATE scheduled_blocks
        SET employee_id = (
            SELECT employee_id FROM scheduled_block_employee
            WHERE block_id = scheduled_blocks.id LIMIT 1
        )
        """
    )

    op.drop_index(
        "ix_scheduled_block_employee_block_id", "scheduled_block_employee"
    )
    op.drop_table("scheduled_block_employee")
    op.drop_index("ix_scheduled_block_role_block_id", "scheduled_block_role")
    op.drop_table("scheduled_block_role")
