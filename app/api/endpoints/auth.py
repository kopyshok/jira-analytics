from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import create_access_token, decode_access_token, verify_password
from app.database import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.user import LoginRequest, TokenResponse, UserResponse

router = APIRouter()
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
_repo = UserRepository()


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
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
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(token: str | None = Depends(_oauth2), db: Session = Depends(get_db)) -> UserResponse:
    if not token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    try:
        payload = decode_access_token(token)
        user_id: str = payload["sub"]
    except (JWTError, KeyError):
        raise HTTPException(status_code=401, detail="Невалидный токен")
    user = _repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return UserResponse.model_validate(user)
