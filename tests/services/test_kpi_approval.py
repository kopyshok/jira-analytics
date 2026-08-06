"""Утверждение месяца KPI: гонка при одновременном закрытии, повторное утверждение."""
from datetime import datetime
from unittest import mock

from sqlalchemy.orm import Query

from app.models.kpi import KpiApproval
from app.services.kpi.kpi_service import save_approval


def test_save_approval_handles_concurrent_insert(db_session):
    """ВАЖНО 3: двое руководителей закрывают месяц одновременно — второй не падает 500,
    а обновляет уже вставленную соперником строку."""
    existing = KpiApproval(
        team="Платежи", year=2026, month=7,
        approved_by="Первый", approved_at=datetime(2026, 7, 30, 10, 0),
        payload_json="{}",
    )
    db_session.add(existing)
    db_session.commit()

    original_first = Query.first
    call_state = {"n": 0}

    def fake_first(self):
        # Первый вызов внутри save_approval имитирует состояние гонки: строка
        # уже есть в базе (только что вставлена «соперником»), но наш процесс
        # ещё не увидел её на шаге чтения.
        if call_state["n"] == 0:
            call_state["n"] += 1
            return None
        return original_first(self)

    with mock.patch.object(Query, "first", fake_first):
        row = save_approval(
            db_session, "Платежи", 2026, 7, "Второй",
            datetime(2026, 7, 30, 11, 0), "{}",
        )

    assert row.approved_by == "Второй"
    rows = db_session.query(KpiApproval).filter_by(team="Платежи", year=2026, month=7).all()
    assert len(rows) == 1


def test_save_approval_reapprove_keeps_latest_approver(db_session):
    """Повторное утверждение другим человеком — остаётся имя последнего утвердившего."""
    save_approval(db_session, "Платежи", 2026, 7, "Первый", datetime(2026, 7, 30, 10, 0), "{}")
    row = save_approval(db_session, "Платежи", 2026, 7, "Второй", datetime(2026, 7, 30, 11, 0), "{}")

    assert row.approved_by == "Второй"
    rows = db_session.query(KpiApproval).filter_by(team="Платежи", year=2026, month=7).all()
    assert len(rows) == 1
    assert rows[0].approved_by == "Второй"
