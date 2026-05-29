"""lowercase user emails

Revision ID: 054_lowercase_emails
Revises: 053_usage_analytics
Create Date: 2026-05-29

Делает логин нечувствительным к регистру: нормализует все существующие
email в нижний регистр. Перед изменением проверяет, что нет коллизий
после нормализации (например, ``User@x`` и ``user@x``); если есть —
миграция падает с понятным сообщением, дальше — ручная склейка.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "054_lowercase_emails"
down_revision: Union[str, None] = "053_usage_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    conflicts = bind.execute(
        sa.text(
            """
            SELECT LOWER(email) AS norm, COUNT(*) AS cnt
            FROM users
            GROUP BY LOWER(email)
            HAVING COUNT(*) > 1
            """
        )
    ).all()
    if conflicts:
        details = ", ".join(f"{row[0]} (x{row[1]})" for row in conflicts)
        raise RuntimeError(
            "Невозможно нормализовать email в нижний регистр: "
            f"коллизии после LOWER — {details}. "
            "Сначала вручную разрули дубликаты в таблице users."
        )
    op.execute(
        sa.text("UPDATE users SET email = LOWER(email) WHERE email <> LOWER(email)")
    )


def downgrade() -> None:
    # Восстановить исходный регистр невозможно — данные потеряны.
    pass
