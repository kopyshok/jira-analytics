"""kpi: шесть метрик и профиль «Аналитик» по умолчанию

Revision ID: k07a_kpi_seed_defaults
Revises: k08a_kpi_profile_is_default
Create Date: 2026-07-30

Идёт ПОСЛЕ k08a, хотя порядковый номер меньше: на чистой базе миграции
применяются по цепочке ``down_revision``, а не по имени файла.

Вставка идёт по ЗАМОРОЖЕННОМУ списку колонок этой ревизии, а не через
ORM-модели. Модель растёт (новые колонки, новые связанные таблицы), а
миграция обязана работать на схеме своего времени: дважды установка с нуля
падала именно на этом — «нет такой колонки» и «нет такой таблицы». Данные
сида берутся из ``app.services.kpi.seed`` как обычные словари: значения,
появившиеся позже, здесь молча отбрасываются, их доставляют более поздние
миграции.
"""
import uuid
from datetime import datetime
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k07a_kpi_seed_defaults"
down_revision: Union[str, None] = "k08a_kpi_profile_is_default"
branch_labels = None
depends_on = None

# Колонки, существующие на этой ревизии (kpi_metrics создан в k05a).
METRIC_COLUMNS = (
    "id", "code", "name", "description", "calc_kind", "numerator_json",
    "denominator_json", "fact_field", "score_fields", "score_max", "invert",
    "cap_at_100", "is_builtin", "sort_order", "created_at", "updated_at",
)
PROFILE_COLUMNS = (
    "id", "code", "name", "target_pct", "warn_band_pct", "is_enabled",
    "created_at", "updated_at",
)
PROFILE_METRIC_COLUMNS = (
    "id", "profile_id", "metric_id", "weight", "sort_order",
    "created_at", "updated_at",
)


def _table(name: str, columns: tuple[str, ...]) -> sa.Table:
    return sa.table(name, *(sa.column(c) for c in columns))


def _row(values: dict, columns: tuple[str, ...], now: datetime) -> dict:
    """Строка ровно по колонкам этой ревизии, с идентификатором и датами.

    Ключи одинаковые у всех строк пачки (недостающие — ``None``): пакетная
    вставка требует единого набора параметров.
    """
    row = {c: values.get(c) for c in columns}
    row["id"] = values.get("id") or str(uuid.uuid4())
    row["created_at"] = now
    row["updated_at"] = now
    return row


def upgrade() -> None:
    # Только данные, без моделей: см. шапку файла.
    from app.services.kpi.seed import METRIC_SEEDS, PROFILE_METRIC_WEIGHTS, PROFILE_SEED

    bind = op.get_bind()
    now = datetime.utcnow()

    # Идемпотентность: миграцию применяют и к уже заполненной базе при
    # пересборке dev-окружения.
    existing_metrics = {
        code for (code,) in bind.execute(sa.text("SELECT code FROM kpi_metrics"))
    }
    new_metrics = [
        _row(seed, METRIC_COLUMNS, now)
        for seed in METRIC_SEEDS if seed["code"] not in existing_metrics
    ]
    if new_metrics:
        op.bulk_insert(_table("kpi_metrics", METRIC_COLUMNS), new_metrics)

    profile_id = bind.execute(
        sa.text("SELECT id FROM kpi_profiles WHERE code = :code"),
        {"code": PROFILE_SEED["code"]},
    ).scalar()
    if profile_id is None:
        profile_row = _row(PROFILE_SEED, PROFILE_COLUMNS, now)
        profile_id = profile_row["id"]
        op.bulk_insert(_table("kpi_profiles", PROFILE_COLUMNS), [profile_row])

    metric_ids = {
        code: mid
        for code, mid in bind.execute(sa.text("SELECT code, id FROM kpi_metrics"))
    }
    linked = {
        mid for (mid,) in bind.execute(
            sa.text("SELECT metric_id FROM kpi_profile_metrics WHERE profile_id = :pid"),
            {"pid": profile_id},
        )
    }
    links = [
        _row(
            {"profile_id": profile_id, "metric_id": metric_ids[code],
             "weight": weight, "sort_order": sort_order},
            PROFILE_METRIC_COLUMNS, now,
        )
        for code, weight, sort_order in PROFILE_METRIC_WEIGHTS
        if code in metric_ids and metric_ids[code] not in linked
    ]
    if links:
        op.bulk_insert(_table("kpi_profile_metrics", PROFILE_METRIC_COLUMNS), links)


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
