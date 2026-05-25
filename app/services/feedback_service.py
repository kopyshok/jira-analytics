"""FeedbackService — баги и идеи от пользователей."""
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.feedback import FeedbackItem, FeedbackKind
from app.models.user import User
from app.schemas.feedback import AttachmentRef, BugCreate, IdeaCreate

_ALLOWED_MIME_PREFIXES = ("image/",)
_ALLOWED_MIME_EXACT = {"application/pdf", "text/plain", "application/json"}
_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


class FeedbackService:
    def __init__(self, attachments_dir: str | None = None) -> None:
        self.attachments_dir = attachments_dir or "data/feedback_attachments"

    def create_bug(
        self, db: Session, *, author: User, payload: BugCreate
    ) -> FeedbackItem:
        item = FeedbackItem(
            kind=FeedbackKind.bug,
            author_id=author.id,
            title=payload.title,
            body=payload.body,
            page_url=payload.page_url,
            steps_to_reproduce=payload.steps_to_reproduce,
            expected=payload.expected,
            actual=payload.actual,
            context_json=(
                json.dumps(payload.context.model_dump()) if payload.context else None
            ),
            attachments_json=(
                json.dumps([a.model_dump() for a in payload.attachments])
                if payload.attachments
                else None
            ),
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def create_idea(
        self, db: Session, *, author: User, payload: IdeaCreate
    ) -> FeedbackItem:
        item = FeedbackItem(
            kind=FeedbackKind.idea,
            author_id=author.id,
            title=payload.title,
            body=payload.body,
            page_url=payload.page_url,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    def list_for_admin(
        self,
        db: Session,
        *,
        kind: FeedbackKind,
        filter_mode: str = "unread",
        limit: int = 200,
        offset: int = 0,
    ) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if filter_mode == "unread":
            stmt = stmt.where(FeedbackItem.read_at.is_(None))
        elif filter_mode == "read":
            stmt = stmt.where(FeedbackItem.read_at.is_not(None))
        stmt = stmt.order_by(FeedbackItem.created_at.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars())

    def list_for_user(
        self,
        db: Session,
        *,
        author_id: str,
        kind: FeedbackKind,
        scope: str = "mine",
        limit: int = 200,
        offset: int = 0,
    ) -> list[FeedbackItem]:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if scope == "mine":
            stmt = stmt.where(FeedbackItem.author_id == author_id)
        stmt = stmt.order_by(FeedbackItem.created_at.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).scalars())

    def mark_read(self, db: Session, *, ids: list[str], reader_id: str) -> int:
        now = datetime.utcnow()
        items = list(
            db.execute(select(FeedbackItem).where(FeedbackItem.id.in_(ids))).scalars()
        )
        for item in items:
            if item.read_at is None:
                item.read_at = now
                item.read_by = reader_id
        db.commit()
        return len(items)

    def mark_unread(self, db: Session, *, ids: list[str]) -> int:
        items = list(
            db.execute(select(FeedbackItem).where(FeedbackItem.id.in_(ids))).scalars()
        )
        for item in items:
            item.read_at = None
            item.read_by = None
        db.commit()
        return len(items)

    def export_markdown(
        self,
        db: Session,
        *,
        kind: FeedbackKind,
        ids: list[str] | None,
        only_unread: bool,
        mark_after: bool,
        reader_id: str | None = None,
    ) -> str:
        stmt = select(FeedbackItem).where(FeedbackItem.kind == kind)
        if only_unread:
            stmt = stmt.where(FeedbackItem.read_at.is_(None))
        if ids:
            stmt = stmt.where(FeedbackItem.id.in_(ids))
        stmt = stmt.order_by(FeedbackItem.created_at.desc())
        items = list(db.execute(stmt).scalars())

        # Pre-load authors to avoid lazy-load after commit.
        author_ids = {it.author_id for it in items}
        authors = {
            u.id: u
            for u in db.execute(
                select(User).where(User.id.in_(author_ids))
            ).scalars()
        }

        header = "# Баги" if kind == FeedbackKind.bug else "# Идеи"
        today = datetime.utcnow().strftime("%Y-%m-%d")
        lines: list[str] = [f"{header} — выгрузка {today} ({len(items)} штук)", ""]

        for idx, it in enumerate(items, start=1):
            author = authors.get(it.author_id)
            display = author.display_name if author else "—"
            email = author.email if author else "—"
            lines.append("---\n")
            lines.append(f"## #{idx} — {it.title}\n")
            lines.append(
                f"**Автор:** {display} ({email})  |  "
                f"**Создан:** {it.created_at.strftime('%Y-%m-%d %H:%M')}  |  "
                f"**URL:** {it.page_url or '—'}\n"
            )
            section_label = "Что случилось" if kind == FeedbackKind.bug else "Описание"
            lines.append(f"### {section_label}\n{it.body}\n")
            if kind == FeedbackKind.bug:
                if it.steps_to_reproduce:
                    lines.append(f"### Шаги воспроизведения\n{it.steps_to_reproduce}\n")
                if it.expected:
                    lines.append(f"### Ожидание\n{it.expected}\n")
                if it.actual:
                    lines.append(f"### Факт\n{it.actual}\n")
                if it.context_json:
                    ctx = json.loads(it.context_json)
                    lines.append("### Контекст")
                    if ctx.get("user_agent"):
                        lines.append(f"- Браузер: {ctx['user_agent']}")
                    if ctx.get("screen_w") and ctx.get("screen_h"):
                        lines.append(f"- Экран: {ctx['screen_w']}×{ctx['screen_h']}")
                    if ctx.get("active_team"):
                        lines.append(f"- Активная команда: {ctx['active_team']}")
                    if ctx.get("active_period"):
                        lines.append(f"- Период: {ctx['active_period']}")
                    if ctx.get("theme"):
                        lines.append(f"- Тема: {ctx['theme']}")
                    lines.append("")
                    ce = ctx.get("console_errors") or []
                    if ce:
                        lines.append(f"### Консольные ошибки ({len(ce)})")
                        for i, e in enumerate(ce, start=1):
                            msg = e.get("message", "")
                            stack = e.get("stack", "")
                            lines.append(f"{i}. `{msg}`" + (f" — {stack}" if stack else ""))
                        lines.append("")
                    ne = ctx.get("network_errors") or []
                    if ne:
                        lines.append(f"### Сетевые ошибки ({len(ne)})")
                        for i, e in enumerate(ne, start=1):
                            lines.append(
                                f"{i}. `{e.get('method', '')} {e.get('url', '')} "
                                f"{e.get('status', '')}` → {e.get('detail', '')}"
                            )
                        lines.append("")
                if it.attachments_json:
                    atts = json.loads(it.attachments_json)
                    if atts:
                        lines.append(f"### Приложения ({len(atts)})")
                        for a in atts:
                            lines.append(
                                f"- `{a['filename']}` → /api/v1/feedback/attachments/{a['path']}"
                            )
                        lines.append("")

        if mark_after and items:
            if reader_id is None:
                raise ValueError("reader_id required when mark_after=True")
            self.mark_read(db, ids=[it.id for it in items], reader_id=reader_id)

        return "\n".join(lines)

    def save_attachment(
        self, *, filename: str, mime: str, data: bytes
    ) -> AttachmentRef:
        if len(data) > _MAX_ATTACHMENT_BYTES:
            raise ValueError("Файл слишком большой (>5 МБ)")
        if not (
            any(mime.startswith(p) for p in _ALLOWED_MIME_PREFIXES)
            or mime in _ALLOWED_MIME_EXACT
        ):
            raise ValueError(f"Тип файла не разрешён: {mime}")
        Path(self.attachments_dir).mkdir(parents=True, exist_ok=True)
        ext = os.path.splitext(filename)[1] or ""
        stored_name = f"{uuid.uuid4()}{ext}"
        full = Path(self.attachments_dir) / stored_name
        full.write_bytes(data)
        return AttachmentRef(filename=filename, mime=mime, size=len(data), path=stored_name)

    def attachment_full_path(self, stored_name: str) -> Path:
        # Защита от path traversal.
        safe = os.path.basename(stored_name)
        return Path(self.attachments_dir) / safe
