"""PlanEditService — ручная правка плановых часов + журнал.

См. spec docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md.
"""
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import Issue, PlanAudit

ROLES = ("analyst", "dev", "qa", "opo")


class PlanEditService:
    def __init__(self, db: Session):
        self.db = db

    def edit(
        self,
        issue_id: str,
        role_hours: Dict[str, Optional[float]],
        comment: str,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Ручная правка планов по ролям + audit-запись на каждую изменённую роль."""
        if not comment or len(comment.strip()) < 1:
            raise ValueError("Comment is required for manual edits")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        for role, new_value in role_hours.items():
            if role not in ROLES:
                continue
            field_manual = f"planned_{role}_hours_manual"
            before = getattr(issue, f"planned_{role}_hours")  # effective
            current_manual = getattr(issue, field_manual)
            # No-op если значение не меняется (manual совпадает с new_value)
            if current_manual == new_value:
                continue
            setattr(issue, field_manual, new_value)
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=new_value,
                source="manual_edit", user_id=user_id, comment=comment,
                created_at=datetime.utcnow(),
            ))
        self.db.commit()
        return issue

    def revert(
        self,
        issue_id: str,
        audit_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Откат: без audit_id — все роли к Jira (manual=None);
        с audit_id — конкретная роль к зафиксированному значению (manual = value_after или None если value_after = jira_now)."""
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        if audit_id is None:
            for role in ROLES:
                field_manual = f"planned_{role}_hours_manual"
                if getattr(issue, field_manual) is None:
                    continue
                before = getattr(issue, f"planned_{role}_hours")
                setattr(issue, field_manual, None)
                after = getattr(issue, f"planned_{role}_hours_jira")
                self.db.add(PlanAudit(
                    issue_id=issue.id, role=role,
                    value_before=before, value_after=after,
                    source="manual_revert", user_id=user_id,
                    comment="Сброс к Jira",
                    created_at=datetime.utcnow(),
                ))
        else:
            audit = self.db.query(PlanAudit).filter_by(id=audit_id).one()
            field_manual = f"planned_{audit.role}_hours_manual"
            field_jira = f"planned_{audit.role}_hours_jira"
            target = audit.value_after
            jira_now = getattr(issue, field_jira)
            before = getattr(issue, f"planned_{audit.role}_hours")
            if target == jira_now:
                setattr(issue, field_manual, None)
            else:
                setattr(issue, field_manual, target)
            self.db.add(PlanAudit(
                issue_id=issue.id, role=audit.role,
                value_before=before, value_after=target,
                source="manual_revert", user_id=user_id,
                comment=f"Откат к записи {audit_id}",
                created_at=datetime.utcnow(),
            ))
        self.db.commit()
        return issue

    def history(self, issue_id: str) -> list[PlanAudit]:
        return (
            self.db.query(PlanAudit)
            .filter_by(issue_id=issue_id)
            .order_by(PlanAudit.created_at.desc(), PlanAudit.id.desc())
            .all()
        )
