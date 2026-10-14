"""Ворклоги за огромный период: потоком, пачками и без гигантских IN-запросов.

После переезда полная синхронизация перечитывает все ворклоги с самой ранней
даты — сотни тысяч записей. Их нельзя копить в памяти целиком и нельзя
отправлять в базу одним ``IN (...)``: у SQLite предел на число параметров.
"""
import re
from datetime import date, datetime

import pytest
from sqlalchemy import event

from app.connectors.schemas import JiraWorklogAuthorSchema, JiraWorklogSchema
from app.models import Employee, Issue, Project, Worklog
from app.services.sync_service import SyncService

KNOWN_ISSUES = ("1001", "1002", "1003")
PER_ISSUE = 900  # 2700 ворклогов известных задач — три пачки
UNKNOWN_ISSUES = 600  # задачи вне базы, у каждой свой id
IN_LIMIT = 500


def _worklog(wl_id: str, issue_id: str, started: str, author: str = "a1",
             seconds: int = 7200) -> JiraWorklogSchema:
    return JiraWorklogSchema(
        id=wl_id,
        issueId=issue_id,
        author=JiraWorklogAuthorSchema(key=author, displayName=author),
        started=started,
        timeSpentSeconds=seconds,
        created=started,
        updated=started,
    )


def _stream(started: str) -> list[JiraWorklogSchema]:
    """Ворклоги известных задач вперемешку с ворклогами задач вне базы."""
    out: list[JiraWorklogSchema] = []
    for n in range(PER_ISSUE):
        for i, jira_id in enumerate(KNOWN_ISSUES):
            author = "a1" if n % 2 else "a2"
            out.append(_worklog(f"w{i}-{n}", jira_id, started, author=author))
        if n < UNKNOWN_ISSUES:
            out.append(_worklog(f"u-{n}", f"9{n:05d}", started))
    return out


class FakeJira:
    def __init__(self, db, worklogs, deleted_ids=()):
        self.db = db
        self.worklogs = worklogs
        self.deleted_ids = list(deleted_ids)
        self.rows_mid_stream: int | None = None
        self.commits_mid_stream: int | None = None
        # Тестовая SQLite — одно соединение на все сессии: вторая сессия видит и
        # незакоммиченное. Поэтому фиксацию пачек считаем по самим коммитам.
        self.commits = 0
        event.listen(db, "after_commit", self._on_commit)

    def _on_commit(self, session):
        self.commits += 1

    async def get_worklogs_updated_since(self, since_dt):
        for wl in self.worklogs:
            yield wl
        # Поток ещё не закончился, а часть ворклогов из него уже записана.
        self.rows_mid_stream = (
            self.db.query(Worklog).filter(Worklog.time_spent_seconds == 7200).count()
        )
        self.commits_mid_stream = self.commits

    async def iter_deleted_worklog_ids(self, since_dt):
        for wl_id in self.deleted_ids:
            yield wl_id


IN_RE = re.compile(r"\bIN\s*\(", re.IGNORECASE)


@pytest.fixture
def queries(engine):
    """Все одиночные запросы теста: ``(текст, число параметров)``."""
    seen: list[tuple[str, int]] = []

    def spy(conn, cursor, statement, parameters, context, executemany):
        if not executemany:
            seen.append((statement, len(parameters)))

    event.listen(engine, "before_cursor_execute", spy)
    yield seen
    event.remove(engine, "before_cursor_execute", spy)


def _assert_batched(queries: list[tuple[str, int]]) -> None:
    """Ни один IN не длиннее предела; задачи не читаются всей таблицей."""
    in_sizes = [n for statement, n in queries if IN_RE.search(statement)]
    assert in_sizes and max(in_sizes) <= IN_LIMIT
    issue_selects = [st for st, _ in queries if re.search(r"\bFROM issues\b", st)]
    assert issue_selects
    assert all(IN_RE.search(st) for st in issue_selects), issue_selects


@pytest.fixture
def base(db_session):
    db_session.add(Project(id="p1", jira_project_id="100", key="PRJ", name="PRJ"))
    db_session.add(Employee(id="e1", jira_account_id="a1", display_name="a1", is_active=True))
    for n, jira_id in enumerate(KNOWN_ISSUES, start=1):
        db_session.add(Issue(
            id=f"i{n}", jira_issue_id=jira_id, key=f"PRJ-{n}", summary="x",
            project_id="p1", issue_type="Task", status="В работе",
        ))
    db_session.commit()


def _local(db, wl_id: str, issue_id: str, started_at: datetime) -> None:
    db.add(Worklog(
        id=wl_id, jira_worklog_id=wl_id, issue_id=issue_id, employee_id="e1",
        started_at=started_at, hours=1.0, time_spent_seconds=3600,
    ))


async def test_update_v2_streams_in_chunks(db_session, base, queries):
    # 600 ворклогов первой задачи уже в базе — Jira прислала их новую версию.
    for n in range(600):
        _local(db_session, f"w0-{n}", "i1", datetime(2026, 4, 1, 9, 0))
    # 700 ворклогов удалены в Jira.
    for n in range(700):
        _local(db_session, f"d-{n}", "i3", datetime(2026, 4, 1, 9, 0))
    db_session.commit()

    jira = FakeJira(
        db_session, _stream("2026-04-02T10:00:00.000+0000"),
        deleted_ids=[f"d-{n}" for n in range(700)],
    )
    stats = await SyncService(db_session, jira).update_worklogs_v2(date(2026, 4, 1))

    known = len(KNOWN_ISSUES) * PER_ISSUE
    assert stats.bucket_a_worklogs_upserted == known
    assert stats.bucket_a_worklogs_deleted == 700
    assert stats.touched_issue_keys == {"PRJ-1", "PRJ-2", "PRJ-3"}
    assert db_session.query(Worklog).count() == known
    assert db_session.query(Worklog).filter(Worklog.jira_worklog_id.like("u-%")).count() == 0
    assert db_session.query(Worklog).filter(Worklog.jira_worklog_id.like("d-%")).count() == 0
    updated = db_session.query(Worklog).filter_by(jira_worklog_id="w0-599").one()
    assert updated.hours == 2.0
    assert updated.time_spent_seconds == 7200
    # Новый автор заведён один раз, старый не задвоен.
    assert db_session.query(Employee).count() == 2
    a2 = db_session.query(Employee).filter_by(jira_account_id="a2").one()
    assert db_session.query(Worklog).filter_by(employee_id=a2.id).count() == known // 2
    assert jira.rows_mid_stream and jira.rows_mid_stream > 0
    assert jira.commits_mid_stream and jira.commits_mid_stream >= 2
    _assert_batched(queries)


async def test_reload_v2_bulk_streams_in_chunks(db_session, base, queries):
    for n in range(800):
        _local(db_session, f"old-{n}", "i2", datetime(2026, 4, 5, 9, 0))
    db_session.commit()

    worklogs = _stream("2026-04-02T10:00:00.000+0000")
    # Исторический дрейф: ворклог изменён недавно, но списан до даты перезагрузки.
    worklogs += [_worklog(f"drift-{n}", "1001", "2026-03-01T10:00:00.000+0000")
                 for n in range(50)]
    progress: list[tuple[int, str | None]] = []

    async def on_progress(stats, key):
        progress.append((stats.worklogs_inserted, key))

    jira = FakeJira(db_session, worklogs)
    stats = await SyncService(db_session, jira).reload_worklogs_v2_bulk(
        date(2026, 4, 1), on_progress=on_progress,
    )

    known = len(KNOWN_ISSUES) * PER_ISSUE
    assert stats.deleted == 800
    assert stats.issues_scanned == len(KNOWN_ISSUES)
    assert stats.worklogs_inserted == known
    assert db_session.query(Worklog).count() == known
    assert db_session.query(Employee).count() == 2
    assert progress[0] == (0, None)
    assert progress[-1][0] == known
    assert jira.rows_mid_stream and jira.rows_mid_stream > 0
    assert jira.commits_mid_stream and jira.commits_mid_stream >= 2
    _assert_batched(queries)


async def test_update_v2_small_input_unchanged(db_session, base):
    """Мало ворклогов — одна неполная пачка, результат прежний."""
    jira = FakeJira(db_session, [
        _worklog("s1", "1001", "2026-04-02T10:00:00.000+0000"),
        _worklog("s2", "1002", "2026-04-02T10:00:00.000+0000"),
        _worklog("s3", "77777", "2026-04-02T10:00:00.000+0000"),
    ])
    stats = await SyncService(db_session, jira).update_worklogs_v2(date(2026, 4, 1))

    assert stats.bucket_a_worklogs_upserted == 2
    assert stats.touched_issue_keys == {"PRJ-1", "PRJ-2"}
    assert {w.jira_worklog_id for w in db_session.query(Worklog)} == {"s1", "s2"}
