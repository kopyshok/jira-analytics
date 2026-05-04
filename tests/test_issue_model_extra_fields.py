from app.models.issue import Issue


def test_issue_has_goal_text_and_current_behavior_columns():
    cols = {c.name for c in Issue.__table__.columns}
    assert "goal_text" in cols
    assert "current_behavior" in cols
