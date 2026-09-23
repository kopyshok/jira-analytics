"""PlanEditService — ручная правка плановых часов + журнал.

См. spec docs/superpowers/specs/2026-06-03-rfa-epic-hierarchy-design.md.
"""
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models import BacklogItem, Issue, PlanAudit
from app.services.backlog_service import BacklogService
from app.services.plan_sources import MANUAL_SOURCE, candidates_from_json, fingerprint

ROLES = ("analyst", "dev", "qa", "opo")


class PlanEditService:
    def __init__(self, db: Session):
        self.db = db

    def _sync_backlog(self, issue: Issue) -> None:
        """Перенести действующие часы задачи в её строку бэклога.

        Строка списка, сценарии и ресурсный план читают копию часов в строке
        бэклога; без этого вызова ручная правка появлялась там только после
        следующего синка. Задача вне бэклога — ничего не создаём.

        Строку в архиве полное выравнивание не трогает: оно вернуло бы её из
        архива и добавило в черновики сценариев. Часы же в любом случае (и в
        архиве, и когда задача только что ушла из бэклога) равны действующим
        часам задачи.
        """
        item = self.db.query(BacklogItem).filter_by(issue_id=issue.id).one_or_none()
        if item is None:
            return
        if item.archived_at is None:
            BacklogService(self.db).sync_from_issue(issue)
        for role in ROLES:
            setattr(item, f"estimate_{role}_hours", getattr(issue, f"planned_{role}_hours"))
        item.estimate_hours = sum(
            getattr(item, f"estimate_{role}_hours") or 0 for role in ROLES
        ) or None

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
        self._sync_backlog(issue)
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
        self._sync_backlog(issue)
        self.db.commit()
        return issue

    def history(self, issue_id: str) -> list[PlanAudit]:
        return (
            self.db.query(PlanAudit)
            .filter_by(issue_id=issue_id)
            .order_by(PlanAudit.created_at.desc(), PlanAudit.id.desc())
            .all()
        )

    def resolve_conflict(
        self,
        issue_id: str,
        role: str,
        action: str,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Разрешает конфликт sync-vs-ручная.

        action='accept_jira' — _manual → None (принять Jira-значение).
        action='ignore' — оставить _manual как есть, закрыть конфликт.
        """
        if role not in ROLES:
            raise ValueError("Unknown role")
        if action not in ("accept_jira", "ignore"):
            raise ValueError("Unknown action")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        field_jira = f"planned_{role}_hours_jira"
        field_manual = f"planned_{role}_hours_manual"
        jira_now = getattr(issue, field_jira)
        before = getattr(issue, f"planned_{role}_hours")  # effective
        if action == "accept_jira":
            setattr(issue, field_manual, None)
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=jira_now,
                source="conflict_accepted", user_id=user_id,
                comment="Принято Jira-значение",
                created_at=datetime.utcnow(),
            ))
        else:  # ignore
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=before,
                source="conflict_ignored", user_id=user_id,
                comment="Конфликт проигнорирован, ручная правка сохранена",
                created_at=datetime.utcnow(),
            ))
        self._sync_backlog(issue)
        self.db.commit()
        return issue

    def choose_source(
        self,
        issue_id: str,
        role: str,
        source: str,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Спорная оценка: сделать действующим одно из полей Jira.

        Выбор запоминается с отпечатком кандидатов: любое изменение значений
        в Jira делает его недействительным, и спор открывается снова.
        Ручное значение роли снимается — пользователь явно выбрал поле Jira.
        """
        if role not in ROLES:
            raise ValueError("Unknown role")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        candidates = candidates_from_json((issue.planned_hours_sources or {}).get(role))
        picked = next((c for c in candidates if c.source == source), None)
        if picked is None:
            raise ValueError("Такого значения нет среди полей Jira этой задачи")
        before = getattr(issue, f"planned_{role}_hours")
        choice = dict(issue.planned_hours_choice or {})
        choice[role] = {"source": source, "fingerprint": fingerprint(candidates)}
        issue.planned_hours_choice = choice  # новый dict — иначе JSON-колонка не заметит правку
        setattr(issue, f"planned_{role}_hours_jira", picked.value)
        setattr(issue, f"planned_{role}_hours_manual", None)
        if before != picked.value:
            self.db.add(PlanAudit(
                issue_id=issue.id, role=role,
                value_before=before, value_after=picked.value,
                source="dispute_choice", user_id=user_id,
                comment=f"Спорная оценка: выбрано «{picked.label}»",
                created_at=datetime.utcnow(),
            ))
        self._sync_backlog(issue)
        self.db.commit()
        return issue

    def choose_manual(
        self,
        issue_id: str,
        role: str,
        value: float,
        user_id: Optional[str] = None,
    ) -> Issue:
        """Спорная оценка: «Ввести своё» — ручное значение роли.

        Спор считается решённым, пока совпадает отпечаток кандидатов и
        у роли есть ручное значение.
        """
        if role not in ROLES:
            raise ValueError("Unknown role")
        issue = self.db.query(Issue).filter_by(id=issue_id).one()
        candidates = candidates_from_json((issue.planned_hours_sources or {}).get(role))
        if not candidates:
            raise ValueError("У роли нет значений из Jira")
        choice = dict(issue.planned_hours_choice or {})
        choice[role] = {"source": MANUAL_SOURCE, "fingerprint": fingerprint(candidates)}
        issue.planned_hours_choice = choice
        # edit (часть 1.5) пишет журнал, синкает копию в бэклоге и коммитит.
        return self.edit(
            issue_id, {role: value}, "Спорная оценка: введено своё значение",
            user_id=user_id,
        )

    def open_conflicts(self, issue_id: str) -> list[dict]:
        """Открытые (не разрешённые) конфликты per роль.

        Для каждой роли смотрим самую свежую audit-запись:
        - если source='jira_sync_conflict' и ниже неё нет 'conflict_accepted'/
          'conflict_ignored'/'manual_edit'/'manual_revert' для той же роли —
          конфликт открыт.
        """
        rows = (
            self.db.query(PlanAudit)
            .filter_by(issue_id=issue_id)
            .order_by(PlanAudit.created_at.desc(), PlanAudit.id.desc())
            .all()
        )
        seen_role: dict = {}
        open_per_role: dict = {}
        for r in rows:
            if r.role in seen_role:
                continue
            seen_role[r.role] = True
            if r.source == "jira_sync_conflict":
                open_per_role[r.role] = r
        return [
            {
                "role": role, "audit_id": audit.id,
                "value_jira": audit.value_after, "value_before": audit.value_before,
            }
            for role, audit in open_per_role.items()
        ]
