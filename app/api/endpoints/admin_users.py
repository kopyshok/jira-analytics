import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.database import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import PasswordReset, UserCreate, UserResponse, UserUpdate

router = APIRouter()
_repo = UserRepository()


@router.get("/", response_model=list[UserResponse])
def list_users(db: Session = Depends(get_db)) -> list[UserResponse]:
    return _repo.list_all(db)


@router.post("/", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db)) -> UserResponse:
    if _repo.get_by_email(db, data.email):
        raise HTTPException(status_code=409, detail="Email уже используется")
    user = User(
        id=str(uuid.uuid4()),
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
        role=data.role,
        default_team=data.default_team,
        is_active=True,
    )
    return _repo.create(db, user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: str, data: UserUpdate, db: Session = Depends(get_db)) -> UserResponse:
    user = _repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.role is not None:
        user.role = data.role
    if data.default_team is not None:
        user.default_team = data.default_team
    if data.is_active is not None:
        user.is_active = data.is_active
    return _repo.update(db, user)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_password(user_id: str, data: PasswordReset, db: Session = Depends(get_db)) -> UserResponse:
    user = _repo.get_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    user.password_hash = hash_password(data.new_password)
    return _repo.update(db, user)
