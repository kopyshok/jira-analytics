"""resource_plan_watch — список наблюдения ресурсного плана

Revision ID: wl01_plan_watchlist
Revises: iv01_clear_frozen_involvement
Create Date: 2026-10-04

Люди любых команд, чью загрузку план показывает в «Загрузке по дням»
секцией «Наблюдаемые» (подбор разработчиков техкомандой). Список общий для
плана. Удаление плана или сотрудника убирает строки.

Самодостаточна: не импортирует код приложения. Локальная база получает
таблицу раньше миграции — от create_all в тестах; тогда пропускаем.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op

revision: str = "wl01_plan_watchlist"
down_revision: Union[str, None] = "iv01_clear_frozen_involvement"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "resource_plan_watch"


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table(TABLE):
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "plan_id", sa.String(36),
            sa.ForeignKey("resource_plans.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "employee_id", sa.String(36),
            sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        # Покрывает и выборку по плану — отдельный индекс не нужен.
        sa.UniqueConstraint("plan_id", "employee_id", name="uq_resource_plan_watch"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
