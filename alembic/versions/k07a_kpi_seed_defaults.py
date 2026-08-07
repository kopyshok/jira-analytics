"""kpi: шесть метрик и профиль «Аналитик» по умолчанию

Revision ID: k07a_kpi_seed_defaults
Revises: k08a_kpi_profile_is_default
Create Date: 2026-07-30

Идёт ПОСЛЕ k08a (колонка ``is_default``), хотя порядковый номер меньше:
``seed_defaults()`` пишет профиль через ORM-модель ``KpiProfile``, у которой
эта колонка уже объявлена в коде. На чистой базе миграции применяются по
цепочке ``down_revision``, а не по имени файла — раньше сидинг шёл раньше
колонки и падал на «no such column» (см. ревью Фазы 4, BLOCKER 3).
"""
from typing import Union

from alembic import op

revision: str = "k07a_kpi_seed_defaults"
down_revision: Union[str, None] = "k08a_kpi_profile_is_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy.orm import Session

    from app.services.kpi.seed import seed_defaults

    bind = op.get_bind()
    session = Session(bind=bind)
    # Без ролей: таблица связи «профиль — роль» появляется только в k13a, она же
    # заводит роли профиля «Аналитик». Сегодняшний seed_defaults() пишет туда, и
    # на чистой базе это падало «relation kpi_profile_roles does not exist».
    seed_defaults(session, with_roles=False)
    session.commit()


def downgrade() -> None:
    # `is_builtin = true` — булев литерал SQL, а не `= 1`: последнее ломается
    # на PostgreSQL (сравнение boolean с integer недопустимо), тогда как
    # `true`/`false` понимают и SQLite (3.23+), и PostgreSQL одинаково.
    #
    # Удаление весов ограничено профилем 'analyst' и встроенными метриками —
    # раньше `DELETE FROM kpi_profile_metrics` без условия стирало веса ЛЮБЫХ
    # профилей, включая заведённые руководителем вручную после сида (см.
    # ревью Фазы 3, ВАЖНО 8).
    op.execute("""
        DELETE FROM kpi_profile_metrics
        WHERE profile_id IN (SELECT id FROM kpi_profiles WHERE code = 'analyst')
           OR metric_id IN (SELECT id FROM kpi_metrics WHERE is_builtin = true)
    """)
    op.execute("DELETE FROM kpi_profiles WHERE code = 'analyst'")
    op.execute("DELETE FROM kpi_metrics WHERE is_builtin = true")
