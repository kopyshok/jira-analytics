import json
from datetime import datetime, timezone

from app.models.user import User, UserRole
from app.schemas.user import UserResponse


def test_userresponse_includes_selected_teams():
    user = User(
        id="x",
        email="a@b.c",
        password_hash="h",
        display_name="A",
        role=UserRole.manager,
        default_team="T",
        is_active=True,
    )
    user.selected_teams = ["T1", "T2"]
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    payload = UserResponse.model_validate(user).model_dump()
    assert payload["selected_teams"] == ["T1", "T2"]
