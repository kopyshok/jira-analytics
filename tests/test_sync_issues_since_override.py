"""Тесты ``SyncService.sync_issues`` с явной датой отсечки (``since_override``).

Покрывает перечитывание задач с произвольной даты (см.
``POST /sync/issues/reload/stream``): дата должна побеждать и отметку
последней синхронизации, и признак ``incremental``, а сам курсор
``sync_state`` не должен сдвигаться назад.
"""

from datetime import date, datetime
from unittest.mock import MagicMock

from app.models import Project, SyncState
from app.services.sync_service import SyncService


async def test_since_override_wins_over_sync_state_and_incremental_flag(db_session):
    """``since_override`` должен победить и более свежий курсор состояния,
    и включённый ``incremental`` — JQL строится по дате из аргумента."""
    project = Project(jira_project_id="10001", key="PRJ", name="Project")
    db_session.add(project)
    db_session.add(SyncState(entity_name="issues", scope="", last_success_at=datetime(2026, 6, 1)))
    db_session.commit()

    captured_jql: list[str] = []

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        captured_jql.append(jql)
        return
        yield  # pragma: no cover

    mock_jira = MagicMock()
    mock_jira.iter_issues = fake_iter_issues

    service = SyncService(db_session, mock_jira)
    await service.sync_issues(
        project_keys=["PRJ"], incremental=True, since_override=date(2026, 1, 1),
    )

    assert len(captured_jql) == 1
    assert '"2026-01-01' in captured_jql[0]
    assert "2026-06-01" not in captured_jql[0]


async def test_since_override_does_not_move_sync_cursor_backward(db_session):
    """Перечитывание с давней даты не должно откатить курсор к этой дате —
    иначе обычный синк начнёт перечитывать лишнее."""
    project = Project(jira_project_id="10002", key="PRJ2", name="Project2")
    db_session.add(project)
    db_session.add(SyncState(entity_name="issues", scope="", last_success_at=datetime(2026, 6, 1)))
    db_session.commit()

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        return
        yield  # pragma: no cover

    mock_jira = MagicMock()
    mock_jira.iter_issues = fake_iter_issues

    service = SyncService(db_session, mock_jira)
    before = datetime.utcnow()
    await service.sync_issues(project_keys=["PRJ2"], since_override=date(2020, 1, 1))
    after = datetime.utcnow()

    state = (
        db_session.query(SyncState)
        .filter_by(entity_name="issues", scope="")
        .one()
    )
    assert before <= state.last_success_at <= after
    assert state.last_success_at.date() != date(2020, 1, 1)


async def test_since_override_none_falls_back_to_normal_incremental_cursor(db_session):
    """Без ``since_override`` поведение прежнее: JQL строится по курсору
    состояния (регрессия обычного режима)."""
    project = Project(jira_project_id="10003", key="PRJ3", name="Project3")
    db_session.add(project)
    db_session.add(SyncState(entity_name="issues", scope="", last_success_at=datetime(2026, 6, 1)))
    db_session.commit()

    captured_jql: list[str] = []

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        captured_jql.append(jql)
        return
        yield  # pragma: no cover

    mock_jira = MagicMock()
    mock_jira.iter_issues = fake_iter_issues

    service = SyncService(db_session, mock_jira)
    await service.sync_issues(project_keys=["PRJ3"], incremental=True)

    assert len(captured_jql) == 1
    assert '"2026-06-01' in captured_jql[0]
