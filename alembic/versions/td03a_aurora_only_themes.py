"""themes: keep only Aurora dark/light

Revision ID: td03a_aurora_only_themes
Revises: td02a_team_desk_marks
Create Date: 2026-08-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "td03a_aurora_only_themes"
down_revision: Union[str, None] = "td02a_team_desk_marks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY = ("dark", "dark-blue", "dark-slate", "dark-charcoal")


def upgrade() -> None:
    # Все прежние темы сводим к тёмной Aurora — других в продукте не осталось.
    op.execute(
        sa.text(
            "UPDATE users SET selected_theme = 'aurora-dark' "
            "WHERE selected_theme IS NULL OR selected_theme NOT IN ('aurora-dark', 'aurora-light')"
        )
    )
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "selected_theme",
            existing_type=sa.String(20),
            existing_nullable=False,
            server_default="aurora-dark",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "selected_theme",
            existing_type=sa.String(20),
            existing_nullable=False,
            server_default="dark-blue",
        )
    # Обратно значения не восстанавливаем: какая тема стояла до слияния,
    # в базе не сохранилось.
