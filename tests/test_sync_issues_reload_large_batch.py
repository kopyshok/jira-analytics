"""Перечитывание задач с начала года не упирается в лимит подстановок SQLite.

SQLite не принимает больше 32766 значений в одном условии IN. Перечитывание
задач с 1 января приносит десятки тысяч ключей, поэтому и поиск задач по
ключам, и пересчёт категорий обязаны идти порциями.
"""
import uuid

from app.models.issue import Issue
from app.models.project import Project
from app.services.mapping_service import MappingService

OVER_SQLITE_LIMIT = 40_000


def _make_project(db) -> Project:
    project = Project(
        jira_project_id=f"p-{uuid.uuid4().hex[:8]}",
        key=f"T{uuid.uuid4().hex[:4].upper()}",
        name="Тестовый проект",
    )
    db.add(project)
    db.commit()
    return project


def test_recalculate_for_issues_handles_more_ids_than_sqlite_allows(db_session):
    """Пересчёт категорий по сорока тысячам задач не падает на лимите подстановок.

    Реальные строки создаём только для сотни задач — остальные идентификаторы
    вымышленные. Проверяется именно то, что запрос разбивается на порции:
    без разбиения SQLite отвечает «too many SQL variables» ещё до того, как
    доберётся до данных.
    """
    project = _make_project(db_session)
    real_ids: list[str] = []
    for i in range(100):
        issue = Issue(
            jira_issue_id=f"big-{i}",
            key=f"{project.key}-{i}",
            summary="Задача",
            issue_type="Задача",
            status="ГОТОВО",
            project_id=project.id,
        )
        db_session.add(issue)
        real_ids.append(issue.id)
    db_session.commit()

    padded = real_ids + [str(uuid.uuid4()) for _ in range(OVER_SQLITE_LIMIT)]
    affected = MappingService(db_session).recalculate_for_issues(padded)

    assert affected >= 0  # падения нет — это и есть проверяемое поведение
