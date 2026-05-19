"""Бэкфилл дефолтной цепочки analyst→dev→qa→opo для существующих планов.

После фикса `_ensure_default_predecessors` (сеялка на уровень инициативы,
а не плана) старые планы могут содержать инициативы без входящих связей —
они были добавлены через auto-sync `initiatives_rfa` после первого расчёта
плана, когда ранний выход «есть хоть одна связь в плане» блокировал
посев. Этот скрипт досевает цепочки таким инициативам.

Запуск:
    py -3.10 scripts/backfill_default_predecessors.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# Allow importing app from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    PhasePredecessor,
    ResourcePlan,
    ResourcePlanAssignment,
)
from app.services.resource_planning_service import PHASE_ORDER  # noqa: E402


def main(dry_run: bool) -> int:
    db = SessionLocal()
    try:
        plans = db.execute(select(ResourcePlan)).scalars().all()
        total_seeded = 0
        total_items_seeded = 0
        for plan in plans:
            assignments = (
                db.execute(
                    select(ResourcePlanAssignment).where(
                        ResourcePlanAssignment.plan_id == plan.id
                    )
                )
                .scalars()
                .all()
            )
            if not assignments:
                continue

            # Какие инициативы уже имеют входящие рёбра.
            rows = (
                db.execute(
                    select(ResourcePlanAssignment.backlog_item_id)
                    .join(
                        PhasePredecessor,
                        PhasePredecessor.successor_assignment_id
                        == ResourcePlanAssignment.id,
                    )
                    .where(ResourcePlanAssignment.plan_id == plan.id)
                    .distinct()
                )
                .all()
            )
            items_with_edges = {r[0] for r in rows}

            by_item: dict[str, dict[str, ResourcePlanAssignment]] = defaultdict(dict)
            for a in assignments:
                by_item[a.backlog_item_id][a.phase] = a

            items_seeded_this_plan = 0
            edges_seeded_this_plan = 0
            for item_id, phases in by_item.items():
                if item_id in items_with_edges:
                    continue
                chain = [
                    phases.get(p) for p in PHASE_ORDER if phases.get(p) is not None
                ]
                if len(chain) < 2:
                    continue
                items_seeded_this_plan += 1
                for i in range(1, len(chain)):
                    succ = chain[i]
                    pred = chain[i - 1]
                    if not succ or not pred or not succ.id or not pred.id:
                        continue
                    if not dry_run:
                        db.add(
                            PhasePredecessor(
                                successor_assignment_id=succ.id,
                                predecessor_assignment_id=pred.id,
                            )
                        )
                    edges_seeded_this_plan += 1

            if items_seeded_this_plan:
                print(
                    f"  plan={plan.id[:8]} label={plan.label!r}: "
                    f"{items_seeded_this_plan} инициатив, {edges_seeded_this_plan} рёбер"
                )
                total_items_seeded += items_seeded_this_plan
                total_seeded += edges_seeded_this_plan

        if not dry_run:
            db.commit()
            print(
                f"\n✓ Применено: {total_items_seeded} инициатив, {total_seeded} рёбер"
            )
        else:
            print(
                f"\n[DRY-RUN] Будет посеяно: {total_items_seeded} инициатив, "
                f"{total_seeded} рёбер. Запустить без --dry-run для применения."
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Только показать, что будет сделано")
    args = parser.parse_args()
    sys.exit(main(dry_run=args.dry_run))
