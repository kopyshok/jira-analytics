"""kpi: раздел скрыт по умолчанию в «Видимости разделов»

Revision ID: k09a_kpi_hidden_by_default
Revises: k08a_kpi_profile_is_default
Create Date: 2026-07-30
"""
import json
import uuid
from datetime import datetime
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "k09a_kpi_hidden_by_default"
down_revision: Union[str, None] = "k08a_kpi_profile_is_default"
branch_labels = None
depends_on = None

_KEY = "ui_hidden_section_keys"
_ROUTE = "/kpi"


def _read_keys(bind) -> list[str]:
    row = bind.execute(
        sa.text("SELECT value FROM app_settings WHERE key = :key"), {"key": _KEY}
    ).first()
    if not row or not row[0]:
        return []
    try:
        parsed = json.loads(row[0])
    except json.JSONDecodeError:
        return []
    return [str(k) for k in parsed] if isinstance(parsed, list) else []


def upgrade() -> None:
    """Дописать `/kpi` в существующий список скрытых разделов, если его там ещё нет.

    Раздел разрабатывается в отдельной ветке и включается вручную через
    «Настройки → Доступ → Видимость разделов» (см. app/api/endpoints/ui_config.py).
    """
    bind = op.get_bind()
    keys = _read_keys(bind)
    if _ROUTE in keys:
        return
    keys.append(_ROUTE)
    payload = json.dumps(sorted(set(keys)), ensure_ascii=False)
    now = datetime.utcnow().isoformat()

    exists = bind.execute(
        sa.text("SELECT 1 FROM app_settings WHERE key = :key"), {"key": _KEY}
    ).scalar()
    if exists:
        bind.execute(
            sa.text("UPDATE app_settings SET value = :value, updated_at = :now WHERE key = :key"),
            {"value": payload, "now": now, "key": _KEY},
        )
    else:
        bind.execute(
            sa.text(
                "INSERT INTO app_settings (id, key, value, created_at, updated_at) "
                "VALUES (:id, :key, :value, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "key": _KEY, "value": payload, "now": now},
        )


def downgrade() -> None:
    """Убрать `/kpi` из списка скрытых разделов, оставив остальные ключи как есть."""
    bind = op.get_bind()
    keys = _read_keys(bind)
    if _ROUTE not in keys:
        return
    keys = [k for k in keys if k != _ROUTE]
    now = datetime.utcnow().isoformat()
    bind.execute(
        sa.text("UPDATE app_settings SET value = :value, updated_at = :now WHERE key = :key"),
        {"value": json.dumps(sorted(keys), ensure_ascii=False), "now": now, "key": _KEY},
    )
