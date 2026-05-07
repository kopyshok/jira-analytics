"""WorkTypeClassifier — Map-фаза: разметка задач по словарю + ведро Другое."""
import pytest
from unittest.mock import AsyncMock

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.issue import Issue
from app.models.project import Project
from app.models.issue_classification import IssueClassification
from app.services.llm.work_type_classifier import (
    WorkTypeClassifier, ClassificationResult, build_input_hash,
)


@pytest.fixture
def fixture_setup(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt); db_session.commit()
    proj = Project(jira_project_id="P", key="PROJ", name="Proj")
    db_session.add(proj); db_session.commit()
    issue = Issue(jira_issue_id="i1", key="PROJ-1",
                  summary="Ошибка обмена", description="d",
                  goal_text="g", current_behavior="b",
                  issue_type="Task", status="Done", project_id=proj.id)
    db_session.add(issue); db_session.commit()
    return {"wt": wt, "issue": issue}


def test_input_hash_stable(fixture_setup):
    issue = fixture_setup["issue"]
    h1 = build_input_hash(issue, worklog_comments=["c1", "c2"])
    h2 = build_input_hash(issue, worklog_comments=["c1", "c2"])
    assert h1 == h2 and len(h1) == 64


def test_input_hash_changes_on_summary_edit(fixture_setup):
    issue = fixture_setup["issue"]
    h1 = build_input_hash(issue, worklog_comments=[])
    issue.summary = "Другое"
    h2 = build_input_hash(issue, worklog_comments=[])
    assert h1 != h2


@pytest.mark.asyncio
async def test_classify_creates_classification(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    theme = Theme(work_type_id=wt.id, name="Ошибки обмена")
    db_session.add(theme); db_session.commit()

    fake_provider = AsyncMock()
    fake_provider.model = "test-model"
    fake_provider.classify_issue = AsyncMock(return_value=(
        ClassificationResult(theme_id=theme.id, candidate_name=None,
                             contribution_text="разбор сбоев", confidence=0.9, nature_tag=None),
        {"model": "test-model", "input_tokens": 100, "output_tokens": 30},
    ))

    clf = WorkTypeClassifier(db_session, provider=fake_provider)
    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[theme])
    assert cls.theme_id == theme.id and cls.contribution_text == "разбор сбоев"
    assert cls.input_hash and cls.dictionary_version == wt.theme_dict_version
    assert cls.failed is False


@pytest.mark.asyncio
async def test_classify_cached_skips_llm(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    theme = Theme(work_type_id=wt.id, name="X")
    db_session.add(theme); db_session.commit()

    fake_provider = AsyncMock(); fake_provider.model = "m"; fake_provider.classify_issue = AsyncMock()
    clf = WorkTypeClassifier(db_session, provider=fake_provider)

    # Pre-seed classification with current input_hash
    h = build_input_hash(issue, worklog_comments=[])
    db_session.add(IssueClassification(
        issue_id=issue.id, work_type_id=wt.id, theme_id=theme.id,
        contribution_text="cached", input_hash=h, dictionary_version=wt.theme_dict_version,
    ))
    db_session.commit()

    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[theme])
    assert cls.contribution_text == "cached"
    fake_provider.classify_issue.assert_not_called()


@pytest.mark.asyncio
async def test_dictionary_version_change_invalidates_cache(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    theme = Theme(work_type_id=wt.id, name="X")
    db_session.add(theme); db_session.commit()

    h = build_input_hash(issue, worklog_comments=[])
    db_session.add(IssueClassification(
        issue_id=issue.id, work_type_id=wt.id, theme_id=theme.id,
        input_hash=h, dictionary_version=max(wt.theme_dict_version - 1, 0),  # stale
    ))
    db_session.commit()

    fake_provider = AsyncMock(); fake_provider.model = "m"
    fake_provider.classify_issue = AsyncMock(return_value=(
        ClassificationResult(theme_id=theme.id, candidate_name=None,
                             contribution_text="fresh", confidence=0.8, nature_tag=None),
        {"model": "m"},
    ))
    clf = WorkTypeClassifier(db_session, provider=fake_provider)
    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[theme])
    assert cls.contribution_text == "fresh"


@pytest.mark.asyncio
async def test_classify_failure_marks_failed_not_raise(fixture_setup, db_session):
    wt, issue = fixture_setup["wt"], fixture_setup["issue"]
    fake = AsyncMock(); fake.model = "m"
    fake.classify_issue = AsyncMock(side_effect=RuntimeError("LLM down"))
    clf = WorkTypeClassifier(db_session, provider=fake)
    cls = await clf.classify_issue(issue=issue, work_type_id=wt.id, themes=[])
    assert cls.failed is True and cls.failure_reason
