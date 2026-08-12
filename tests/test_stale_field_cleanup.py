"""Чистка мёртвого поля «Разработчик» у переехавших задач."""
import asyncio
import uuid

from app.models import AppSetting, Issue, Project
from app.services.stale_field_cleanup import clear_stale_developer_field

FIELD_ID = "customfield_14052"


class FakeJira:
    """Отдаёт поля карточки по типу задачи; считает опросы."""

    def __init__(self, fields_by_type: dict[str, set[str]], fail: bool = False):
        self.fields_by_type = fields_by_type
        self.fail = fail
        self.probes: list[str] = []
        self.types_by_key: dict[str, str] = {}

    async def get_editable_field_ids(self, issue_key: str) -> set[str]:
        self.probes.append(issue_key)
        if self.fail:
            raise RuntimeError("нет прав на карточку")
        return self.fields_by_type.get(self.types_by_key.get(issue_key, ""), set())


def _project(db_session, key: str) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        jira_project_id=str(uuid.uuid4()),
        key=key,
        name=key,
    )
    db_session.add(project)
    db_session.flush()
    return project


def _issue(db_session, jira, project, key, issue_type="Задача", developer="acc-1"):
    row = Issue(
        id=str(uuid.uuid4()),
        jira_issue_id=str(uuid.uuid4()),
        key=key,
        summary=key,
        issue_type=issue_type,
        status="В РАБОТЕ",
        project_id=project.id,
        developer_account_id=developer,
        developer_display_name="Кирилов Константин" if developer else None,
    )
    db_session.add(row)
    db_session.flush()
    jira.types_by_key[key] = issue_type
    return row


def _configure_field(db_session):
    db_session.add(
        AppSetting(id=str(uuid.uuid4()), key="jira_developer_field_id", value=FIELD_ID)
    )
    db_session.flush()


def test_project_without_field_is_cleared(db_session):
    """Задача уехала в проект, где поля «Разработчик» нет — значение мёртвое."""
    _configure_field(db_session)
    jira = FakeJira({"Задача": {FIELD_ID, "summary"}, "БФТ": {"summary"}})
    dev_project = _project(db_session, "OS")
    office = _project(db_session, "PMD")
    _issue(db_session, jira, dev_project, "OS-1")
    _issue(db_session, jira, office, "PMD-1", issue_type="БФТ")
    db_session.commit()

    result = asyncio.run(clear_stale_developer_field(db_session, jira))

    assert result["issues_cleared"] == 1
    assert result["projects_stale"] == 1
    rows = {i.key: i for i in db_session.query(Issue).all()}
    assert rows["PMD-1"].developer_account_id is None
    assert rows["PMD-1"].developer_display_name is None
    assert rows["OS-1"].developer_account_id == "acc-1"


def test_type_without_field_in_live_project_is_kept(db_session):
    """Поле принадлежит проекту: тип без поля на карточке — не повод чистить.

    В проекте разработки заявки поддержки поля на карточке не показывают, но
    значение там осмысленное. Раз в проекте поле есть хотя бы на одном типе —
    проект живой целиком.
    """
    _configure_field(db_session)
    jira = FakeJira({"Задача": {FIELD_ID}, "Support": {"summary"}})
    dev_project = _project(db_session, "OS")
    _issue(db_session, jira, dev_project, "OS-1")
    _issue(db_session, jira, dev_project, "OS-2", issue_type="Support")
    db_session.commit()

    result = asyncio.run(clear_stale_developer_field(db_session, jira))

    assert result["issues_cleared"] == 0
    assert all(i.developer_account_id == "acc-1" for i in db_session.query(Issue).all())


def test_live_project_stops_probing_early(db_session):
    """Нашли поле на первой же карточке — остальные типы не опрашиваем."""
    _configure_field(db_session)
    jira = FakeJira({"Задача": {FIELD_ID}})
    project = _project(db_session, "OS")
    for n in range(4):
        _issue(db_session, jira, project, f"OS-{n}")
    db_session.commit()

    asyncio.run(clear_stale_developer_field(db_session, jira))

    # Один тип задач, опрошено не больше трёх карточек и ни одной лишней.
    assert len(jira.probes) <= 3


def test_probe_failure_keeps_data(db_session):
    """Опрос не удался — данные не трогаем: сбой связи не повод их терять."""
    _configure_field(db_session)
    jira = FakeJira({"БФТ": {"summary"}}, fail=True)
    office = _project(db_session, "PMD")
    _issue(db_session, jira, office, "PMD-1", issue_type="БФТ")
    db_session.commit()

    result = asyncio.run(clear_stale_developer_field(db_session, jira))

    assert result["issues_cleared"] == 0
    assert db_session.query(Issue).one().developer_account_id == "acc-1"


def test_dry_run_changes_nothing(db_session):
    """Режим показа считает, но данные не трогает."""
    _configure_field(db_session)
    jira = FakeJira({"БФТ": {"summary"}})
    office = _project(db_session, "PMD")
    _issue(db_session, jira, office, "PMD-1", issue_type="БФТ")
    db_session.commit()

    result = asyncio.run(clear_stale_developer_field(db_session, jira, dry_run=True))

    assert result["issues_cleared"] == 1
    assert db_session.query(Issue).one().developer_account_id == "acc-1"


def test_field_not_configured_is_noop(db_session):
    """Поле не настроено — чистить нечего и не по чему."""
    jira = FakeJira({})
    project = _project(db_session, "OS")
    _issue(db_session, jira, project, "OS-1")
    db_session.commit()

    result = asyncio.run(clear_stale_developer_field(db_session, jira))

    assert result == {"projects_checked": 0, "projects_stale": 0, "issues_cleared": 0}
    assert not jira.probes
