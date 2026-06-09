"""Cleanup: убрать из draft-сценариев allocations на инициативы,
уже включённые в утверждённый сценарий.

Раньше при создании / автосинке сценария включённые в approved-сценарии
инициативы всё равно попадали в новые draft-сценарии. PM-у казалось,
что задача доступна повторно в следующем квартале.

Чистим только allocations с included_flag=False — если PM в draft уже
поставил галочку (редкий случай намеренного дубля), не сносим, оставляем
PM разруливать вручную.

Revision ID: 062_cleanup_draft_allocations_for_approved_included
Revises: 061_employee_teams_joined_at
Create Date: 2026-06-09
"""
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "062_cleanup_draft_allocations_for_approved_included"
down_revision: Union[str, None] = "061_employee_teams_joined_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    meta = sa.MetaData()
    meta.reflect(bind=bind, only=["scenario_allocations", "planning_scenarios"])
    alloc = meta.tables["scenario_allocations"]
    scen = meta.tables["planning_scenarios"]

    approved_included_items = (
        sa.select(alloc.c.backlog_item_id)
        .select_from(alloc.join(scen, scen.c.id == alloc.c.scenario_id))
        .where(scen.c.status == "approved")
        .where(alloc.c.included_flag.is_(True))
    )

    draft_scenarios = sa.select(scen.c.id).where(scen.c.status == "draft")

    stmt = (
        sa.delete(alloc)
        .where(alloc.c.included_flag.is_(False))
        .where(alloc.c.scenario_id.in_(draft_scenarios))
        .where(alloc.c.backlog_item_id.in_(approved_included_items))
    )
    bind.execute(stmt)


def downgrade() -> None:
    # Восстановить удалённые строки невозможно — это data cleanup, не схема.
    pass
