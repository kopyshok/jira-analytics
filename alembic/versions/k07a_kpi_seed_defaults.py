"""kpi: шесть метрик и профиль «Аналитик» по умолчанию

Revision ID: k07a_kpi_seed_defaults
Revises: k06a_kpi_issue_jira_created_at
Create Date: 2026-07-30
"""
from typing import Union

from alembic import op

revision: str = "k07a_kpi_seed_defaults"
down_revision: Union[str, None] = "k06a_kpi_issue_jira_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy.orm import Session

    from app.services.kpi.seed import seed_defaults

    bind = op.get_bind()
    session = Session(bind=bind)
    seed_defaults(session)
    session.commit()


def downgrade() -> None:
    # `is_builtin = true` — булев литерал SQL, а не `= 1`: последнее ломается
    # на PostgreSQL (сравнение boolean с integer недопустимо), тогда как
    # `true`/`false` понимают и SQLite (3.23+), и PostgreSQL одинаково.
    op.execute("DELETE FROM kpi_profile_metrics")
    op.execute("DELETE FROM kpi_profiles WHERE code = 'analyst'")
    op.execute("DELETE FROM kpi_metrics WHERE is_builtin = true")
