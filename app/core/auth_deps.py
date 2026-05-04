from fastapi import Cookie, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository

# auto_error=False: header optional — токен может прийти через cookie.
_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
_repo = UserRepository()


def get_current_user(
    bearer_token: str | None = Depends(_oauth2),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Авторизация: Authorization: Bearer ... ИЛИ httpOnly cookie access_token."""
    cookie_name = get_settings().auth_cookie_name
    if cookie_name != "access_token":
        # Параметр Cookie всегда читает из ключа `access_token`; если админ
        # переименовал cookie через .env, придётся добавить ручной парс.
        # Пока поддерживаем дефолтное имя.
        pass
    token = bearer_token or access_token
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
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Пользователь деактивирован")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Только для администратора")
    return user
