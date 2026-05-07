"""WorkTypeReportService — orchestrator end-to-end tests with fake providers."""
import json
import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock

from app.models.mandatory_work_type import MandatoryWorkType
from app.models.theme import Theme
from app.models.category import Category
from app.models.issue import Issue
from app.models.project import Project
from app.models.employee import Employee
from app.models.worklog import Worklog
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.services.work_type_report_service import (
    WorkTypeReportService, _team_set_hash, _resolve_period,
)
from app.services.llm.work_type_classifier import ClassificationResult
from app.services.llm.work_type_synthesizer import SynthesisOutput


@pytest.fixture
def setup_data(db_session):
    wt = MandatoryWorkType(code="support_consult", label="Сопр", sort_order=1)
    db_session.add(wt)
    db_session.commit()

    cat = Category(code="support_consultation", label="Сопровождение", work_type_id=wt.id)
    db_session.add(cat)
    db_session.commit()

    proj = Project(jira_project_id="P", key="PROJ", name="Proj")
    db_session.add(proj)
    db_session.commit()

    emp = Employee(jira_account_id="u1", display_name="Иванов И.", team="Платформа", role="analyst")
    db_session.add(emp)
    db_session.commit()

    issue1 = Issue(
        jira_issue_id="i1", key="PROJ-1", summary="Ошибка обмена",
        issue_type="Task", status="Done", project_id=proj.id,
        assigned_category="support_consultation", team="Платформа",
    )
    issue2 = Issue(
        jira_issue_id="i2", key="PROJ-2", summary="Проводка",
        issue_type="Task", status="Done", project_id=proj.id,
        assigned_category="support_consultation", team="Платформа",
    )
    db_session.add_all([issue1, issue2])
    db_session.commit()

    db_session.add_all([
        Worklog(
            jira_worklog_id="w1", issue_id=issue1.id, employee_id=emp.id,
            hours=10.0, time_spent_seconds=36000,
            started_at=datetime(2026, 4, 5),
        ),
        Worklog(
            jira_worklog_id="w2", issue_id=issue2.id, employee_id=emp.id,
            hours=5.0, time_spent_seconds=18000,
            started_at=datetime(2026, 4, 10),
        ),
    ])
    db_session.commit()
    return {"wt": wt, "issue1": issue1, "issue2": issue2, "emp": emp}


def test_team_set_hash_stable():
    h1 = _team_set_hash(["A", "B"])
    h2 = _team_set_hash(["B", "A"])
    h3 = _team_set_hash([])
    assert h1 == h2  # sort-invariant
    assert h3 == "all"


def test_resolve_period_month():
    s, e = _resolve_period(2026, 2, 4)
    assert s == date(2026, 4, 1)
    assert e == date(2026, 4, 30)


def test_resolve_period_quarter():
    s, e = _resolve_period(2026, 2, None)
    assert s == date(2026, 4, 1)
    assert e == date(2026, 6, 30)


@pytest.mark.asyncio
async def test_build_with_empty_dictionary_creates_candidates(setup_data, db_session):
    """All AI classifications go to 'Other' (theme_id=null) → candidates appear in snapshot."""
    wt = setup_data["wt"]

    fake_classifier = AsyncMock()
    fake_classifier.model = "test-classifier"
    fake_classifier.classify_issue = AsyncMock(side_effect=[
        (ClassificationResult(theme_id=None, candidate_name="Ошибки обмена",
                              contribution_text="разбор", confidence=0.8), {"model": "tc"}),
        (ClassificationResult(theme_id=None, candidate_name="Проводки",
                              contribution_text="фикс", confidence=0.7), {"model": "tc"}),
    ])
    fake_synth = AsyncMock()
    fake_synth.model = "test-synth"
    fake_synth.synthesize_work_type_report = AsyncMock(return_value=(
        {
            "headline": "h",
            "themes_narratives": [],
            "outliers_explanations": [],
            "recommendation": {"text": "r", "expected_impact": ""},
        },
        {"model": "test-synth"},
    ))

    svc = WorkTypeReportService(
        db_session,
        classifier_provider=fake_classifier,
        synthesizer_provider=fake_synth,
    )
    snap = await svc.get_or_build(
        work_type_id=wt.id, year=2026, quarter=2, month=4, teams=[],
        force_refresh=False, user_id=None,
    )
    data = json.loads(snap.snapshot_data)
    assert "candidates" in data and len(data["candidates"]) >= 1


@pytest.mark.asyncio
async def test_get_or_build_caches_when_dict_unchanged(setup_data, db_session):
    """Second call returns existing snapshot (no LLM)."""
    wt = setup_data["wt"]
    fake_classifier = AsyncMock()
    fake_classifier.model = "tc"
    fake_classifier.classify_issue = AsyncMock(return_value=(
        ClassificationResult(theme_id=None, candidate_name="X",
                             contribution_text="c", confidence=0.5),
        {"model": "tc"},
    ))
    fake_synth = AsyncMock()
    fake_synth.model = "ts"
    fake_synth.synthesize_work_type_report = AsyncMock(return_value=(
        {
            "headline": "h",
            "themes_narratives": [],
            "outliers_explanations": [],
            "recommendation": {"text": "", "expected_impact": ""},
        },
        {"model": "ts"},
    ))

    svc = WorkTypeReportService(db_session, classifier_provider=fake_classifier,
                                synthesizer_provider=fake_synth)
    snap1 = await svc.get_or_build(
        work_type_id=wt.id, year=2026, quarter=2, month=4,
        teams=[], force_refresh=False, user_id=None,
    )
    call_count_1 = fake_synth.synthesize_work_type_report.call_count
    snap2 = await svc.get_or_build(
        work_type_id=wt.id, year=2026, quarter=2, month=4,
        teams=[], force_refresh=False, user_id=None,
    )
    assert snap1.id == snap2.id
    assert fake_synth.synthesize_work_type_report.call_count == call_count_1  # no new call


@pytest.mark.asyncio
async def test_force_refresh_rebuilds(setup_data, db_session):
    wt = setup_data["wt"]
    fake_classifier = AsyncMock()
    fake_classifier.model = "tc"
    fake_classifier.classify_issue = AsyncMock(return_value=(
        ClassificationResult(theme_id=None, candidate_name="X",
                             contribution_text="c", confidence=0.5),
        {"model": "tc"},
    ))
    fake_synth = AsyncMock()
    fake_synth.model = "ts"
    fake_synth.synthesize_work_type_report = AsyncMock(return_value=(
        {
            "headline": "h",
            "themes_narratives": [],
            "outliers_explanations": [],
            "recommendation": {"text": "", "expected_impact": ""},
        },
        {"model": "ts"},
    ))
    svc = WorkTypeReportService(db_session, classifier_provider=fake_classifier,
                                synthesizer_provider=fake_synth)
    await svc.get_or_build(
        work_type_id=wt.id, year=2026, quarter=2, month=4,
        teams=[], force_refresh=False, user_id=None,
    )
    n1 = fake_synth.synthesize_work_type_report.call_count
    await svc.get_or_build(
        work_type_id=wt.id, year=2026, quarter=2, month=4,
        teams=[], force_refresh=True, user_id=None,
    )
    assert fake_synth.synthesize_work_type_report.call_count == n1 + 1


@pytest.mark.asyncio
async def test_failed_classifications_appear_in_manual_review(setup_data, db_session):
    """Issues that fail classification get listed in manual_review_required."""
    wt = setup_data["wt"]
    fake_classifier = AsyncMock()
    fake_classifier.model = "tc"
    fake_classifier.classify_issue = AsyncMock(side_effect=RuntimeError("LLM down"))
    fake_synth = AsyncMock()
    fake_synth.model = "ts"
    fake_synth.synthesize_work_type_report = AsyncMock(return_value=(
        {
            "headline": "h",
            "themes_narratives": [],
            "outliers_explanations": [],
            "recommendation": {"text": "", "expected_impact": ""},
        },
        {"model": "ts"},
    ))
    svc = WorkTypeReportService(db_session, classifier_provider=fake_classifier,
                                synthesizer_provider=fake_synth)
    snap = await svc.get_or_build(
        work_type_id=wt.id, year=2026, quarter=2, month=4,
        teams=[], force_refresh=False, user_id=None,
    )
    data = json.loads(snap.snapshot_data)
    assert "manual_review_required" in data
    assert len(data["manual_review_required"]) >= 1
