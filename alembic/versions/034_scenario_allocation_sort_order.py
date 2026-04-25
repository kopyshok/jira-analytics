"""Per-scenario manual sort order for allocations.

PM может перетаскивать строки сценария мышкой и переключать включение,
не теряя порядок. ``sort_order`` хранится отдельно от ``BacklogItem.priority``
(который теперь автозабивается из Jira) и принадлежит конкретному сценарию.

Бэкфилл: текущий порядок (priority NULLS LAST, title ASC) фиксируется как
sort_order = 1, 2, 3, ... в рамках каждого сценария.
"""

from alembic import op
import sqlalchemy as sa


revision = "034_scenario_allocation_sort_order"
down_revision = "033_qa_role_color_pink"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("scenario_allocations") as batch:
        batch.add_column(sa.Column("sort_order", sa.Float(), nullable=True))

    # Backfill: проставить sort_order по текущей видимой сортировке.
    # Берём (priority NULLS LAST, title ASC, allocation.id ASC) — стабильно
    # совпадает с тем, что фронт показывал до миграции.
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT
                    sa.id,
                    ROW_NUMBER() OVER (
                        PARTITION BY sa.scenario_id
                        ORDER BY
                            CASE WHEN bi.priority IS NULL THEN 1 ELSE 0 END,
                            bi.priority,
                            COALESCE(bi.title, ''),
                            sa.id
                    ) * 1.0 AS rn
                FROM scenario_allocations sa
                JOIN backlog_items bi ON bi.id = sa.backlog_item_id
            )
            UPDATE scenario_allocations
            SET sort_order = (SELECT rn FROM ordered WHERE ordered.id = scenario_allocations.id)
            WHERE EXISTS (SELECT 1 FROM ordered WHERE ordered.id = scenario_allocations.id);
            """
        )
    )


def downgrade():
    with op.batch_alter_table("scenario_allocations") as batch:
        batch.drop_column("sort_order")
