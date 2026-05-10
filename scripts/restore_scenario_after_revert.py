"""Recovery скрипт: восстановить состав сценария после неполного revert.

Сценарии, которые были approved ДО фикса 2026-05-10 и затем revert'нуты:
  - status уже draft, но
  - связанные issues остались в quarterly_tasks
  - allocations этих задач могут быть либо живы, либо удалены другой логикой

Скрипт:
  1) находит сценарий по id или по имени;
  2) собирает Issue.id, которые вели к этому сценарию (через имеющиеся
     allocations либо через ScenarioRevisionItem последней ревизии);
  3) для каждой задачи в category=quarterly_tasks (и не удерживаемой
     другим approved сценарием) откатывает категорию в initiatives_rfa,
     дёргает CategoryResolver и BacklogService.sync_from_issue;
  4) гарантирует существование ScenarioAllocation с included_flag=True
     в этом сценарии;
  5) commit.

Запуск:
    py -3.10 scripts/restore_scenario_after_revert.py <scenario_id>
    py -3.10 scripts/restore_scenario_after_revert.py --name "Q2 2026 plan"
    py -3.10 scripts/restore_scenario_after_revert.py --dry-run --name "Q2 2026"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    BacklogItem,
    Issue,
    PlanningScenario,
    ScenarioAllocation,
    ScenarioRevision,
    ScenarioRevisionItem,
)
from app.services.backlog_service import BACKLOG_CATEGORY, BacklogService  # noqa: E402
from app.services.category_resolver import CategoryResolver  # noqa: E402


def find_scenario(db, scenario_id: str | None, name: str | None) -> PlanningScenario:
    if scenario_id:
        s = db.get(PlanningScenario, scenario_id)
        if not s:
            sys.exit(f"Scenario id={scenario_id} not found")
        return s
    if name:
        rows = db.execute(
            select(PlanningScenario).where(PlanningScenario.name.ilike(f"%{name}%"))
        ).scalars().all()
        if not rows:
            sys.exit(f"No scenarios match name~={name!r}")
        if len(rows) > 1:
            print("Multiple matches — pick one by id:")
            for r in rows:
                print(f"  {r.id}  {r.name}  Q{r.quarter} {r.year}  status={r.status}")
            sys.exit(2)
        return rows[0]
    sys.exit("provide scenario_id positional arg or --name")


def collect_target_item_ids(db, scenario_id: str) -> set[str]:
    """item_id, которые относятся к этому сценарию.

    Источники: текущие allocations + последняя ScenarioRevisionItem(action='included').
    """
    ids: set[str] = set()
    for (item_id,) in db.execute(
        select(ScenarioAllocation.backlog_item_id).where(
            ScenarioAllocation.scenario_id == scenario_id
        )
    ).all():
        ids.add(item_id)

    last_rev = db.execute(
        select(ScenarioRevision)
        .where(ScenarioRevision.scenario_id == scenario_id)
        .order_by(ScenarioRevision.revision_number.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last_rev:
        for (item_id,) in db.execute(
            select(ScenarioRevisionItem.backlog_item_id).where(
                ScenarioRevisionItem.revision_id == last_rev.id,
                ScenarioRevisionItem.action == "included",
            )
        ).all():
            if item_id:
                ids.add(item_id)
    return ids


def held_by_other_approved(db, item_id: str, this_scenario_id: str) -> bool:
    return (
        db.execute(
            select(ScenarioAllocation.id)
            .join(PlanningScenario, PlanningScenario.id == ScenarioAllocation.scenario_id)
            .where(
                ScenarioAllocation.backlog_item_id == item_id,
                ScenarioAllocation.included_flag.is_(True),
                PlanningScenario.status == "approved",
                PlanningScenario.id != this_scenario_id,
            )
        ).first()
        is not None
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario_id", nargs="?", help="UUID сценария")
    parser.add_argument("--name", help="искать сценарий по имени (LIKE)")
    parser.add_argument("--dry-run", action="store_true", help="ничего не менять, только напечатать план")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        scenario = find_scenario(db, args.scenario_id, args.name)
        print(f"Scenario: {scenario.id}  {scenario.name}  Q{scenario.quarter} {scenario.year}  status={scenario.status}")

        target_ids = collect_target_item_ids(db, scenario.id)
        if not target_ids:
            sys.exit("Нет связанных item_id ни в allocations, ни в ревизиях.")
        print(f"Найдено связанных backlog-items: {len(target_ids)}")

        items = db.execute(
            select(BacklogItem).where(BacklogItem.id.in_(target_ids))
        ).scalars().all()

        resolver = CategoryResolver(db)
        backlog_svc = BacklogService(db)
        plan: list[str] = []

        for item in items:
            issue = db.get(Issue, item.issue_id) if item.issue_id else None
            issue_label = f"{issue.key} {issue.summary[:40]}" if issue else "(no-issue)"

            need_recat = (
                issue is not None
                and issue.category == "quarterly_tasks"
                and not held_by_other_approved(db, item.id, scenario.id)
            )

            existing_alloc = db.execute(
                select(ScenarioAllocation).where(
                    ScenarioAllocation.scenario_id == scenario.id,
                    ScenarioAllocation.backlog_item_id == item.id,
                )
            ).scalar_one_or_none()

            actions = []
            if need_recat:
                actions.append("recat→initiatives_rfa")
            if existing_alloc is None:
                actions.append("create-allocation+included")
            elif not existing_alloc.included_flag:
                actions.append("set included=True")
            else:
                actions.append("alloc already included")

            plan.append(f"  {item.id[:8]}  {issue_label:55s}  → {', '.join(actions)}")

            if args.dry_run:
                continue

            if need_recat:
                issue.assigned_category = "initiatives_rfa"
                issue.category = resolver.resolve_for_issue(issue).category_code
                backlog_svc.sync_from_issue(issue)

            if existing_alloc is None:
                # sync_from_issue выше может уже создать allocation в этом draft —
                # перечитать
                existing_alloc = db.execute(
                    select(ScenarioAllocation).where(
                        ScenarioAllocation.scenario_id == scenario.id,
                        ScenarioAllocation.backlog_item_id == item.id,
                    )
                ).scalar_one_or_none()
            if existing_alloc is None:
                db.add(
                    ScenarioAllocation(
                        scenario_id=scenario.id,
                        backlog_item_id=item.id,
                        included_flag=True,
                        planned_hours=0,
                    )
                )
            else:
                existing_alloc.included_flag = True

        for line in plan:
            print(line)

        if args.dry_run:
            print("\nDRY-RUN — изменения НЕ сохранены.")
            return

        db.commit()
        print("\nГотово. Перезапусти бэкенд если статичный кэш и обнови /planning.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
