from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.auth_deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import LoginRequest, TokenResponse, UserResponse, UserTeamsUpdate

router = APIRouter()
_repo = UserRepository()


def _set_auth_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.auth_cookie_name,
        value=token,
        httponly=True,
        secure=bool(s.auth_cookie_secure),
        samesite=s.auth_cookie_samesite,  # type: ignore[arg-type]
        max_age=s.jwt_expire_hours * 3600,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(key=s.auth_cookie_name, path="/")


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = _repo.get_by_email(db, data.email)
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь деактивирован")
    settings = get_settings()
    token = create_access_token(
        {"sub": user.id, "role": user.role.value, "default_team": user.default_team},
        expires_hours=settings.jwt_expire_hours,
    )
    _set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    _clear_auth_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.put("/me/teams", response_model=UserResponse)
def update_my_teams(
    data: UserTeamsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    user.selected_teams = data.teams
    return UserResponse.model_validate(_repo.update(db, user))
