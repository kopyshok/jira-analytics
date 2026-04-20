"""Backlog без year/quarter; PlanningScenario.status; merge initiatives_backlog→initiatives_rfa.

Revision ID: 024_backlog_no_quarter_scenario_status
Revises: 023_align_employee_roles
Create Date: 2026-04-21

Architectural shift:
- Backlog теперь содержит все задачи категории «Инициативы и RFA» (`initiatives_rfa`)
  без привязки к году/кварталу.
- Квартал — атрибут сценария, не элемента бэклога.
- Сценарий имеет статус `draft` | `approved`: PM собирает план отметками,
  сохраняет черновиком, утверждает для аналитики.

Upgrade:
1. Переносим Issue.category `initiatives_backlog` → `initiatives_rfa`
   (то же для `category_mappings.category` и `backlog_service`-кода).
2. Удаляем категорию `initiatives_backlog` из `categories`.
3. Удаляем колонки `year` и `quarter` из `backlog_items`.
4. Добавляем `status` (String(16), NOT NULL default 'draft') в `planning_scenarios`.

Downgrade — best-effort: колонки восстанавливаются пустыми, категория-сирота
пересоздаётся; привязку issue↔initiatives_backlog восстановить нельзя.
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "024_backlog_no_quarter_scenario_status"
down_revision: Union[str, None] = "023_align_employee_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Перенести issues.category с initiatives_backlog на initiatives_rfa.
    #    И денормализованное поле issues.category, и строки в category_mappings.
    bind.execute(sa.text(
        "UPDATE issues SET category = 'initiatives_rfa' "
        "WHERE category = 'initiatives_backlog'"
    ))
    bind.execute(sa.text(
        "UPDATE issues SET assigned_category = 'initiatives_rfa' "
        "WHERE assigned_category = 'initiatives_backlog'"
    ))
    bind.execute(sa.text(
        "UPDATE category_mappings SET category = 'initiatives_rfa' "
        "WHERE category = 'initiatives_backlog'"
    ))
    bind.execute(sa.text(
        "UPDATE category_overrides SET category_code = 'initiatives_rfa' "
        "WHERE category_code = 'initiatives_backlog'"
    ))

    # 2) Удалить категорию initiatives_backlog. Category.work_type_id — FK с
    #    ondelete=SET NULL, так что ссылающиеся строки не упадут.
    bind.execute(sa.text(
        "DELETE FROM categories WHERE code = 'initiatives_backlog'"
    ))

    # 3) Drop year/quarter из backlog_items.
    with op.batch_alter_table("backlog_items") as b:
        b.drop_column("year")
        b.drop_column("quarter")

    # 4) Add status в planning_scenarios (default 'draft').
    with op.batch_alter_table("planning_scenarios") as b:
        b.add_column(sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="draft",
        ))


def downgrade() -> None:
    # Восстановить колонки (пустыми).
    with op.batch_alter_table("backlog_items") as b:
        b.add_column(sa.Column("year", sa.Integer(), nullable=True))
        b.add_column(sa.Column("quarter", sa.String(10), nullable=True))

    with op.batch_alter_table("planning_scenarios") as b:
        b.drop_column("status")

    # Восстановить категорию initiatives_backlog как сироту.
    bind = op.get_bind()
    existing = bind.execute(
        sa.text("SELECT id FROM categories WHERE code = :c"),
        {"c": "initiatives_backlog"},
    ).fetchone()
    if not existing:
        cats = sa.table(
            "categories",
            sa.column("id", sa.String),
            sa.column("code", sa.String),
            sa.column("label", sa.String),
            sa.column("color", sa.String),
            sa.column("sort_order", sa.Integer),
            sa.column("is_system", sa.Boolean),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        )
        now = datetime.utcnow()
        op.bulk_insert(cats, [{
            "id": str(uuid.uuid4()),
            "code": "initiatives_backlog",
            "label": "Бэклог инициатив",
            "color": "#7F77DD",
            "sort_order": 23,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
        }])
