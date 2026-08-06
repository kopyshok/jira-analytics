"""Пять новых полей Jira попадают в задачу по сопоставлению из настроек."""
from app.models.project import Project
from app.services.sync_service import _extract_single_value


def test_extract_single_value_handles_three_shapes():
    assert _extract_single_value({"cf1": {"value": "PROD"}}, "cf1") == "PROD"
    assert _extract_single_value({"cf1": [{"value": "PROD"}]}, "cf1") == "PROD"
    assert _extract_single_value({"cf1": "PROD"}, "cf1") == "PROD"
    assert _extract_single_value({}, "cf1") is None
    assert _extract_single_value({"cf1": None}, "cf1") is None


def test_issue_custom_field_columns(db_session):
    from app.models.issue import Issue

    project = Project(jira_project_id="p-1", key="OS", name="1С")
    db_session.add(project)
    db_session.flush()

    issue = Issue(
        jira_issue_id="10002", key="OS-2", summary="Тест", issue_type="Задача",
        status="ГОТОВО", project_id=project.id,
        environment="PROD", subtype="RFC_STANDARD", cost_type="Change",
        cycle_time_fact=64.0, direction="Финансовые операции",
    )
    db_session.add(issue)
    db_session.commit()
    loaded = db_session.query(Issue).filter_by(key="OS-2").one()
    assert loaded.environment == "PROD"
    assert loaded.cycle_time_fact == 64.0
