"""Одноразовый скрипт: проставить parent_revision_id для существующих v1-ревизий
по упорядочиванию revision_number внутри каждого сценария.

Запуск: py -3.10 scripts/link_v1_revisions.py [--dry-run]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PlanningScenario, ScenarioRevision


def link(db: Session, dry_run: bool = False) -> dict:
    scenarios = db.query(PlanningScenario).all()
    updated = 0
    for sc in scenarios:
        revs = (
            db.query(ScenarioRevision)
            .filter_by(scenario_id=sc.id)
            .order_by(ScenarioRevision.revision_number.asc())
            .all()
        )
        prev_id: str | None = None
        for rev in revs:
            if rev.parent_revision_id != prev_id:
                if not dry_run:
                    rev.parent_revision_id = prev_id
                updated += 1
            prev_id = rev.id
    if not dry_run:
        db.commit()
    return {"updated": updated, "scenarios": len(scenarios)}


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        result = link(db, dry_run=dry)
        prefix = "DRY-RUN " if dry else ""
        print(f"{prefix}linked: {result['updated']} ревизий в {result['scenarios']} сценариях")
    finally:
        db.close()
