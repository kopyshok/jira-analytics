"""Backlog→Scenarios chain: issue planned hours, backlog item roles, seed category.

Revision ID: 022_backlog_planning_chain
Revises: 021_capacity_v3
Create Date: 2026-04-20
"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision: str = "022_backlog_planning_chain"
down_revision: Union[str, None] = "021_capacity_v3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (code, label, color, sort_order, is_system)
# sort_order=23 — следующий свободный после archive_target (22, см. миграцию 010).
SEED_CATEGORY = (
    "initiatives_backlog",
    "Бэклог инициатив",
    "#7F77DD",
    23,
    True,
)

# AppSetting keys introduced by this feature — admin заполняет через UI,
# в миграции не сидим (пустые "" строки бесполезны: _set_setting — upsert,
# а _configured_planned_field_ids корректно пропускает отсутствующие ключи).
# Оставлено как reference какие ключи ожидает sync.
NEW_SETTING_KEYS = [
    "jira_planned_analyst_hours_field_id",
    "jira_planned_dev_hours_field_id",
    "jira_planned_qa_hours_field_id",
    "jira_planned_opo_hours_field_id",
    "jira_involvement_analyst_field_id",
    "jira_involvement_dev_field_id",
    "jira_involvement_qa_field_id",
    "jira_involvement_launch_field_id",
    "jira_duration_analyst_field_id",
    "jira_duration_dev_field_id",
    "jira_duration_qa_field_id",
    "jira_duration_launch_field_id",
    "jira_impact_field_id",
    "jira_risk_field_id",
]


def upgrade() -> None:
    # --- Issue columns ---
    with op.batch_alter_table("issues") as b:
        b.add_column(sa.Column("planned_analyst_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("planned_dev_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("planned_qa_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("planned_opo_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_analyst", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_dev", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_qa", sa.Float(), nullable=True))
        b.add_column(sa.Column("involvement_launch", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_analyst_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_dev_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_qa_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("duration_launch_days", sa.Float(), nullable=True))
        b.add_column(sa.Column("impact", sa.String(20), nullable=True))
        b.add_column(sa.Column("risk", sa.String(20), nullable=True))

    # --- BacklogItem columns ---
    with op.batch_alter_table("backlog_items") as b:
        b.add_column(sa.Column("issue_id", sa.String(36), nullable=True))
        b.add_column(sa.Column("estimate_analyst_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("estimate_dev_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("estimate_qa_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column("estimate_opo_hours", sa.Float(), nullable=True))
        b.add_column(sa.Column(
            "opo_analyst_ratio", sa.Float(), nullable=True, server_default="0.5"
        ))
        b.add_column(sa.Column("impact", sa.String(20), nullable=True))
        b.add_column(sa.Column("risk", sa.String(20), nullable=True))
        b.create_foreign_key(
            "fk_backlog_items_issue_id",
            "issues",
            ["issue_id"],
            ["id"],
            ondelete="SET NULL",
        )
        b.create_index(
            "ix_backlog_items_issue_id", ["issue_id"], unique=True
        )

    # --- Seed category ---
    bind = op.get_bind()
    code, label, color, sort_order, is_system = SEED_CATEGORY
    existing = bind.execute(
        sa.text("SELECT id FROM categories WHERE code = :c"), {"c": code}
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
            "code": code,
            "label": label,
            "color": color,
            "sort_order": sort_order,
            "is_system": is_system,
            "created_at": now,
            "updated_at": now,
        }])

    # AppSetting keys for customfield IDs не сидим: admin задаёт их через UI,
    # а sync-код (см. _configured_planned_field_ids) корректно пропускает
    # отсутствующие ключи. Пустые "" строки лишь засоряли таблицу.


def downgrade() -> None:
    with op.batch_alter_table("backlog_items") as b:
        b.drop_index("ix_backlog_items_issue_id")
        b.drop_constraint("fk_backlog_items_issue_id", type_="foreignkey")
        for col in [
            "risk", "impact", "opo_analyst_ratio",
            "estimate_opo_hours", "estimate_qa_hours",
            "estimate_dev_hours", "estimate_analyst_hours", "issue_id",
        ]:
            b.drop_column(col)

    with op.batch_alter_table("issues") as b:
        for col in [
            "risk", "impact",
            "duration_launch_days", "duration_qa_days",
            "duration_dev_days", "duration_analyst_days",
            "involvement_launch", "involvement_qa",
            "involvement_dev", "involvement_analyst",
            "planned_opo_hours", "planned_qa_hours",
            "planned_dev_hours", "planned_analyst_hours",
        ]:
            b.drop_column(col)

    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM categories WHERE code = 'initiatives_backlog'"))
    # AppSetting ключи этой фичи в upgrade() не создаются — чистить нечего.
