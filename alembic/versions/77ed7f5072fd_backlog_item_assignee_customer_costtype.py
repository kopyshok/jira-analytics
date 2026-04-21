"""backlog_item_assignee_customer_costtype

Revision ID: 77ed7f5072fd
Revises: 029_backlog_archived_at
Create Date: 2026-04-21 20:56:52.291653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77ed7f5072fd'
down_revision: Union[str, None] = '029_backlog_archived_at'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.add_column(sa.Column(
            "assignee_employee_id",
            sa.String(36),
            sa.ForeignKey("employees.id", ondelete="SET NULL", name="fk_backlog_items_assignee_employee_id"),
            nullable=True,
        ))
        batch_op.add_column(sa.Column("customer", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cost_type", sa.String(50), nullable=True))
        batch_op.create_index(
            "ix_backlog_items_assignee_employee_id",
            ["assignee_employee_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as batch_op:
        batch_op.drop_index("ix_backlog_items_assignee_employee_id")
        batch_op.drop_column("assignee_employee_id")
        batch_op.drop_column("customer")
        batch_op.drop_column("cost_type")
