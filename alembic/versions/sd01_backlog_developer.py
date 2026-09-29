"""backlog_items + scenario_allocation_snapshots: разработчик строки

Revision ID: sd01_backlog_developer
Revises: nw01_normed_reserve
Create Date: 2026-09-28

Разработчик задачи, выбранный вручную в сценарии или на бэклоге; копия — в
снимке утверждённого сценария. Самодостаточна: не импортирует код
приложения. Локальная dev-база может уже иметь колонки от create_all в
tests/conftest.py — такие пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "sd01_backlog_developer"
down_revision: Union[str, None] = "nw01_normed_reserve"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    insp = sa.inspect(op.get_bind())
    return "developer_employee_id" in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    if not _has("backlog_items"):
        with op.batch_alter_table("backlog_items") as batch:
            batch.add_column(sa.Column(
                "developer_employee_id",
                sa.String(36),
                sa.ForeignKey(
                    "employees.id", ondelete="SET NULL",
                    name="fk_backlog_items_developer_employee_id",
                ),
                nullable=True,
            ))
            batch.create_index(
                "ix_backlog_items_developer_employee_id", ["developer_employee_id"]
            )
    if not _has("scenario_allocation_snapshots"):
        with op.batch_alter_table("scenario_allocation_snapshots") as batch:
            batch.add_column(sa.Column("developer_employee_id", sa.String(36), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("scenario_allocation_snapshots") as batch:
        batch.drop_column("developer_employee_id")
    with op.batch_alter_table("backlog_items") as batch:
        batch.drop_index("ix_backlog_items_developer_employee_id")
        batch.drop_column("developer_employee_id")
