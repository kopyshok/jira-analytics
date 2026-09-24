"""resource_plan_assignments: часть ОПЭ хранится у строки

Revision ID: pq07_assignment_opo_part
Revises: pq06_plan_external_fingerprint
Create Date: 2026-09-24

У двух частей ОПЭ (аналитика и разработчика) один номер части. Раньше часть
узнавалась по человеку и его роли, и выбор исполнителя другой роли переносил
строку на чужую часть. Теперь часть хранится у строки.

Заполнение существующих строк ОПЭ — тем же способом, каким часть узнавалась
раньше: исполнитель анализа задачи в том же плане (и не разработки) — часть
аналитика, исполнитель разработки (и не анализа) — часть разработчика, иначе
по роли. Две строки одной части с одним номером разводятся по разным частям.

Самодостаточна: не импортирует код приложения.
"""
from collections import defaultdict
from typing import Dict, List, Sequence, Set, Tuple, Union

from alembic import op
import sqlalchemy as sa

revision: str = "pq07_assignment_opo_part"
down_revision: Union[str, None] = "pq06_plan_external_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ANALYST_ROLES = {"аналитик", "analyst", "an", "рп", "rp", "консультант", "consultant"}

assignments = sa.table(
    "resource_plan_assignments",
    sa.column("id", sa.String),
    sa.column("plan_id", sa.String),
    sa.column("backlog_item_id", sa.String),
    sa.column("phase", sa.String),
    sa.column("employee_id", sa.String),
    sa.column("part_number", sa.Integer),
    sa.column("opo_part", sa.String),
)
employees = sa.table("employees", sa.column("id", sa.String), sa.column("role", sa.String))


def _by_role(role) -> str:
    return "analyst" if (role or "").lower() in ANALYST_ROLES else "dev"


def upgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch:
        batch.add_column(sa.Column("opo_part", sa.String(16), nullable=True))

    bind = op.get_bind()
    role_of = {r.id: r.role for r in bind.execute(sa.select(employees.c.id, employees.c.role))}
    own: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
    opo: Dict[Tuple[str, str, int], List[Tuple[str, str]]] = defaultdict(list)
    for r in bind.execute(
        sa.select(
            assignments.c.id, assignments.c.plan_id, assignments.c.backlog_item_id,
            assignments.c.phase, assignments.c.employee_id, assignments.c.part_number,
        ).order_by(assignments.c.id)
    ):
        if r.phase in ("analyst", "dev") and r.employee_id:
            own[(r.plan_id, r.backlog_item_id, r.phase)].add(r.employee_id)
        elif r.phase == "opo":
            opo[(r.plan_id, r.backlog_item_id, r.part_number)].append(
                (r.id, r.employee_id)
            )

    for (plan_id, item_id, _num), rows in opo.items():
        own_an = own[(plan_id, item_id, "analyst")]
        own_dev = own[(plan_id, item_id, "dev")]
        parts: List[str] = []
        for _id, emp in rows:
            if emp in own_an and emp not in own_dev:
                parts.append("analyst")
            elif emp in own_dev and emp not in own_an:
                parts.append("dev")
            else:
                parts.append(_by_role(role_of.get(emp)))
        if len(rows) == 2 and parts[0] == parts[1]:
            parts[1] = "dev" if parts[0] == "analyst" else "analyst"
        for (row_id, _emp), part in zip(rows, parts):
            bind.execute(
                assignments.update()
                .where(assignments.c.id == row_id)
                .values(opo_part=part)
            )


def downgrade() -> None:
    with op.batch_alter_table("resource_plan_assignments") as batch:
        batch.drop_column("opo_part")
