from app.models.user import UserRole


def test_user_role_values():
    assert UserRole.admin == "admin"
    assert UserRole.super_manager == "super_manager"
    assert UserRole.manager == "manager"
