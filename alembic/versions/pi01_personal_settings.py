"""employee_personal_settings + employee_personal_normed

Revision ID: pi01_personal_settings
Revises: sd01_backlog_developer
Create Date: 2026-09-29

Личная настройка сотрудника с квартала: вовлечённость (главнее задачи и
справочника команды) и свои проценты нормированных работ по видам.

Самодостаточна: не импортирует код приложения. Локальная dev-база может
уже иметь таблицы от create_all в tests/conftest.py — такие пропускаем.
"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

revision: str = "pi01_personal_settings"
down_revision: Union[str, None] = "sd01_backlog_developer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has(table: str) -> bool:
    if context.is_offline_mode():
        return False
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has("employee_personal_settings"):
        op.create_table(
            "employee_personal_settings",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "employee_id", sa.String(36),
                sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("effective_year", sa.Integer(), nullable=False),
            sa.Column("effective_quarter", sa.Integer(), nullable=False),
            sa.Column("involvement", sa.Float(), nullable=True),
            sa.Column("normed_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "employee_id", "effective_year", "effective_quarter",
                name="uq_employee_personal_setting_scope",
            ),
        )
        op.create_index(
            "ix_employee_personal_settings_employee_id",
            "employee_personal_settings", ["employee_id"],
        )
    if not _has("employee_personal_normed"):
        op.create_table(
            "employee_personal_normed",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "setting_id", sa.String(36),
                sa.ForeignKey("employee_personal_settings.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "work_type_id", sa.String(36),
                sa.ForeignKey("mandatory_work_types.id"), nullable=False,
            ),
            sa.Column("percent_of_norm", sa.Float(), nullable=False),
            sa.UniqueConstraint("setting_id", "work_type_id", name="uq_employee_personal_normed"),
        )
        op.create_index(
            "ix_employee_personal_normed_setting_id",
            "employee_personal_normed", ["setting_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_employee_personal_normed_setting_id", table_name="employee_personal_normed")
    op.drop_table("employee_personal_normed")
    op.drop_index(
        "ix_employee_personal_settings_employee_id", table_name="employee_personal_settings"
    )
    op.drop_table("employee_personal_settings")
