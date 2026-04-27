from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

from app.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_hours: int) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=expires_hours)
    return jwt.encode(to_encode, get_settings().jwt_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    """Raises jose.JWTError if token is invalid or expired."""
    return jwt.decode(token, get_settings().jwt_secret_key, algorithms=["HS256"])
