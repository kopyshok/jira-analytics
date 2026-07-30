"""kpi: явный признак профиля по умолчанию

Revision ID: k08a_kpi_profile_is_default
Revises: k06a_kpi_issue_jira_created_at
Create Date: 2026-07-30

Идёт ПЕРЕД k07a (сид метрик и профиля «Аналитик»): сидинг пишет профиль
через ORM-модель ``KpiProfile``, которая уже объявляет колонку
``is_default`` — на чистой базе колонка обязана существовать до первой
вставки (см. ревью Фазы 4, BLOCKER 3). Строку 'analyst' по умолчанию
проставляет сам ``seed_defaults()`` при создании — не отдельным UPDATE
здесь, потому что на момент выполнения этой миграции профиля ещё нет.
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k08a_kpi_profile_is_default"
down_revision: Union[str, None] = "k06a_kpi_issue_jira_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("kpi_profiles") as batch:
        batch.add_column(
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("kpi_profiles") as batch:
        batch.drop_column("is_default")
