"""Синк: несколько полей оценки на роль, спор и выбор."""
import json
from unittest.mock import MagicMock

from app.models import AppSetting, Issue, Project
from app.services.plan_sources import SUM_SOURCE, candidates_from_json, disputes_for, fingerprint
from app.services.sync_service import SyncService, _to_float
from tests.test_sync_service import _make_issue_schema_with_extra

DEV_SETTING = json.dumps([
    {"field_id": "customfield_12432", "kind": "alt", "name": "Разработка (ч)"},
    {"field_id": "customfield_14648", "kind": "alt", "name": "Оценка 1С (ч)"},
    {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"},
    {"field_id": "customfield_12889", "kind": "sum", "name": "Оценка Front"},
], ensure_ascii=False)


def _setup(db):
    db.add(AppSetting(key="jira_planned_dev_hours_field_id", value=DEV_SETTING))
    db.add(AppSetting(key="jira_planned_analyst_hours_field_id", value="customfield_12431"))
    proj = Project(jira_project_id="pps", key="RFA", name="RFA")
    db.add(proj)
    db.commit()
    return SyncService(db, jira_client=MagicMock()), proj


def _upsert(svc, proj, extra):
    schema = _make_issue_schema_with_extra(
        jira_id="90001", key="RFA-900", project_key="RFA", project_id="pps",
        extra_fields=extra,
    )
    svc._upsert_issue(schema, project_id=proj.id)
    svc.db.commit()
    return svc.db.query(Issue).filter_by(jira_issue_id="90001").one()


def test_configured_ids_expand_lists_not_json(db_session):
    svc, _ = _setup(db_session)
    ids = svc._configured_planned_field_ids()
    for fid in ("customfield_12432", "customfield_14648", "customfield_12888",
                "customfield_12889", "customfield_12431"):
        assert fid in ids
    assert not any(i.startswith("[") for i in ids)


def test_legacy_string_setting_still_works(db_session):
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12431": 40})
    assert issue.planned_analyst_hours_jira == 40.0
    assert candidates_from_json(issue.planned_hours_sources["analyst"])[0].value == 40.0


def test_equal_alts_no_dispute_value_set(db_session):
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12432": 100, "customfield_14648": "100"})
    assert issue.planned_dev_hours_jira == 100.0
    assert len(issue.planned_hours_sources["dev"]) == 2


def test_dispute_default_first_then_choice_then_change(db_session):
    svc, proj = _setup(db_session)
    extra = {"customfield_12432": 100, "customfield_12888": 30, "customfield_12889": 50}
    issue = _upsert(svc, proj, extra)
    cands = candidates_from_json(issue.planned_hours_sources["dev"])
    assert [c.source for c in cands] == ["customfield_12432", SUM_SOURCE]
    assert issue.planned_dev_hours_jira == 100.0

    issue.planned_hours_choice = {"dev": {"source": SUM_SOURCE, "fingerprint": fingerprint(cands)}}
    db_session.commit()
    issue = _upsert(svc, proj, extra)
    assert issue.planned_dev_hours_jira == 80.0

    extra["customfield_12889"] = 60
    issue = _upsert(svc, proj, extra)
    assert issue.planned_dev_hours_jira == 100.0


def test_non_finite_values_are_not_numbers():
    for raw in ("nan", "NaN", "inf", "-Infinity", "1e400", float("nan"), float("inf")):
        assert _to_float(raw) is None, raw


def test_non_finite_field_is_not_a_candidate(db_session):
    """NaN из Jira не становится кандидатом: PostgreSQL не примет его в JSONB."""
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12432": "NaN", "customfield_14648": 56})
    assert issue.planned_dev_hours_jira == 56.0
    assert [c.source for c in candidates_from_json(issue.planned_hours_sources["dev"])] == [
        "customfield_14648",
    ]


def test_zero_field_is_not_a_candidate(db_session):
    """«Разработка» = 0, «Оценка 1С» = 56: не спор, действует 56."""
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12432": 0, "customfield_14648": 56})
    assert issue.planned_dev_hours_jira == 56.0
    assert [c.source for c in candidates_from_json(issue.planned_hours_sources["dev"])] == [
        "customfield_14648",
    ]


def test_stale_choice_dropped_so_old_values_reopen_dispute(db_session):
    """Значения в Jira поменялись — синк удаляет устаревший выбор. Вернулись
    старые значения — спор снова открыт, а не решён молча прежним выбором."""
    svc, proj = _setup(db_session)
    old = {"customfield_12432": 100, "customfield_14648": 120}
    issue = _upsert(svc, proj, old)
    cands = candidates_from_json(issue.planned_hours_sources["dev"])
    issue.planned_hours_choice = {"dev": {"source": "customfield_14648", "fingerprint": fingerprint(cands)}}
    db_session.commit()
    issue = _upsert(svc, proj, old)
    assert issue.planned_dev_hours_jira == 120.0
    assert issue.planned_hours_choice is not None

    issue = _upsert(svc, proj, {"customfield_12432": 100, "customfield_14648": 130})
    assert issue.planned_hours_choice is None
    assert _is_sql_null(db_session, Issue.planned_hours_choice)

    issue = _upsert(svc, proj, old)
    assert issue.planned_dev_hours_jira == 100.0
    assert list(disputes_for(issue.planned_hours_sources, issue.planned_hours_choice, set())) == ["dev"]


def test_no_fields_filled_clears_sources(db_session):
    svc, proj = _setup(db_session)
    _upsert(svc, proj, {"customfield_12432": 100})
    issue = _upsert(svc, proj, {})
    assert issue.planned_hours_sources is None
    assert issue.planned_dev_hours_jira is None


def _is_sql_null(db, column) -> bool:
    return db.query(Issue).filter(Issue.jira_issue_id == "90001", column.is_(None)).count() == 1


def test_cleared_json_columns_are_sql_null(db_session):
    """Пустые кандидаты и выбор лежат в базе как SQL NULL, а не как JSON-строка
    'null': иначе условие «IS NULL» таких задач не находит."""
    svc, proj = _setup(db_session)
    issue = _upsert(svc, proj, {"customfield_12432": 100, "customfield_14648": 120})
    cands = candidates_from_json(issue.planned_hours_sources["dev"])
    issue.planned_hours_choice = {"dev": {"source": "customfield_14648", "fingerprint": fingerprint(cands)}}
    db_session.commit()
    assert not _is_sql_null(db_session, Issue.planned_hours_sources)

    issue = _upsert(svc, proj, {})
    issue.planned_hours_choice = None
    db_session.commit()

    assert _is_sql_null(db_session, Issue.planned_hours_sources)
    assert _is_sql_null(db_session, Issue.planned_hours_choice)


async def test_sync_issues_end_to_end_multi_fields(db_session):
    """Полный путь синка: запрос к Jira просит все поля ролей, ответ с
    несколькими полями даёт кандидатов, спор и действующее значение."""
    from app.connectors.schemas import JiraIssueSchema

    db_session.add(AppSetting(key="jira_planned_analyst_hours_field_id", value=json.dumps([
        {"field_id": "customfield_12431", "kind": "alt", "name": "Анализ (ч)"},
        {"field_id": "customfield_14296", "kind": "alt", "name": "Анализ 1С (ч)"},
    ], ensure_ascii=False)))
    db_session.add(AppSetting(key="jira_planned_dev_hours_field_id", value=json.dumps([
        {"field_id": "customfield_12888", "kind": "sum", "name": "Оценка Back"},
        {"field_id": "customfield_12889", "kind": "sum", "name": "Оценка Front"},
    ], ensure_ascii=False)))
    db_session.add(AppSetting(key="jira_planned_qa_hours_field_id", value="customfield_12433"))
    db_session.add(Project(jira_project_id="10500", key="E2E", name="E2E"))
    db_session.commit()

    payload = {
        "id": "95001", "key": "E2E-1",
        "fields": {
            "summary": "Инициатива",
            "issuetype": {"id": "1", "name": "RFA", "subtask": False},
            "status": {"id": "1", "name": "Open", "statusCategory": {"key": "new"}},
            "project": {"id": "10500", "key": "E2E", "name": "E2E"},
            "customfield_12431": 40,
            "customfield_14296": "55,5",
            "customfield_12888": 30,
            "customfield_12889": 50.5,
            "customfield_12433": None,
        },
    }
    captured_fields: list = []

    async def fake_iter_issues(jql, max_results, fields):  # noqa: ARG001
        captured_fields.append(fields)
        yield JiraIssueSchema.model_validate(payload)

    jira = MagicMock()
    jira.iter_issues = fake_iter_issues
    await SyncService(db_session, jira).sync_issues(project_keys=["E2E"], incremental=False)

    requested = captured_fields[0]
    for fid in ("customfield_12431", "customfield_14296", "customfield_12888",
                "customfield_12889", "customfield_12433"):
        assert fid in requested
    assert not any(str(f).startswith("[") for f in requested)

    issue = db_session.query(Issue).filter_by(jira_issue_id="95001").one()
    assert issue.planned_analyst_hours_jira == 40.0  # спор: по умолчанию первое поле
    assert [(c.source, c.value) for c in candidates_from_json(issue.planned_hours_sources["analyst"])] == [
        ("customfield_12431", 40.0), ("customfield_14296", 55.5),
    ]
    dev = candidates_from_json(issue.planned_hours_sources["dev"])
    assert [(c.source, c.label, c.value) for c in dev] == [
        (SUM_SOURCE, "Оценка Back + Оценка Front", 80.5),
    ]
    assert issue.planned_dev_hours_jira == 80.5
    assert "qa" not in issue.planned_hours_sources
    assert issue.planned_qa_hours_jira is None
