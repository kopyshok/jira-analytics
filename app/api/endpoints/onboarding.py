"""«Первые шаги»: статус шагов команды и личное состояние пользователя."""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth_deps import get_current_user
from app.database import get_db
from app.models import User
from app.services import onboarding_service as svc

router = APIRouter()


class StepStatePayload(BaseModel):
    team: str
    state: Literal["done", "skipped", "pending"]


class MePayload(BaseModel):
    completed_tours: Optional[list[str]] = None
    auto_opened: Optional[bool] = None
    hidden: Optional[bool] = None


@router.get("/status")
def get_status(
    team: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Свежее состояние пользователя из БД: current_user из зависимости может
    # быть тем же объектом, что и до правки в /me в рамках одного запроса/теста.
    user = db.get(User, current_user.id) or current_user
    me = svc.me_state(user)
    steps = svc.team_steps(db, team) if team else {}
    return {"team": team, "steps": steps, "me": me}


@router.put("/team-steps/{step}")
def put_team_step(
    step: str,
    payload: StepStatePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if step not in svc.ALL_STEPS:
        raise HTTPException(status_code=404, detail="Неизвестный шаг")
    if payload.state == "done" and step not in svc.MANUAL_STEPS:
        raise HTTPException(status_code=400, detail="Этот шаг отмечается автоматически")
    user_id = current_user.id
    svc.set_team_step(db, payload.team, step, payload.state, user_id)
    return {"ok": True}


@router.put("/me")
def put_me(
    payload: MePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.get(User, current_user.id) or current_user
    state = svc.me_state(user)
    state.update(payload.model_dump(exclude_none=True))
    user.onboarding = state
    db.commit()
    return state
