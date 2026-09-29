"""CRUD личных настроек сотрудника: вовлечённость и свои нормированные работы."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Employee,
    EmployeePersonalNormed,
    EmployeePersonalSetting,
    MandatoryWorkType,
)
from app.services.event_bus import EventBroadcaster, get_event_bus
from app.services.team_membership import members_ever

router = APIRouter()

# Личная настройка меняет раскладку планов и базу сценариев любой команды.
_CHANGED = {"type": "entity_changed", "entities": ["planning", "resource_planning"]}


class NormedIn(BaseModel):
    work_type_id: str
    percent_of_norm: float


class PersonalSettingIn(BaseModel):
    employee_id: str
    effective_year: int = Field(ge=2000, le=2100)
    effective_quarter: int = Field(ge=1, le=4)
    involvement: Optional[float] = None
    normed_custom: bool = False
    normed: List[NormedIn] = []


class NormedOut(BaseModel):
    work_type_id: str
    label: str
    percent_of_norm: float


class PersonalSettingOut(BaseModel):
    id: str
    employee_id: str
    employee_name: str
    employee_role: Optional[str]
    effective_year: int
    effective_quarter: int
    involvement: Optional[float]
    normed_custom: bool
    normed: List[NormedOut]


def _serialize(db: Session, settings: List[EmployeePersonalSetting]) -> List[dict]:
    """Строки ответа: имя и роль сотрудника, проценты — в порядке справочника видов."""
    if not settings:
        return []
    emps = {
        e.id: e
        for e in db.query(Employee).filter(
            Employee.id.in_(list({s.employee_id for s in settings}))
        )
    }
    normed: dict = {s.id: [] for s in settings}
    for n, wt in (
        db.query(EmployeePersonalNormed, MandatoryWorkType)
        .join(MandatoryWorkType, MandatoryWorkType.id == EmployeePersonalNormed.work_type_id)
        .filter(EmployeePersonalNormed.setting_id.in_(list(normed)))
        .order_by(MandatoryWorkType.sort_order, MandatoryWorkType.label)
    ):
        normed[n.setting_id].append(
            {"work_type_id": wt.id, "label": wt.label, "percent_of_norm": n.percent_of_norm}
        )
    return [
        {
            "id": s.id,
            "employee_id": s.employee_id,
            "employee_name": emps[s.employee_id].display_name,
            "employee_role": emps[s.employee_id].role,
            "effective_year": s.effective_year,
            "effective_quarter": s.effective_quarter,
            "involvement": s.involvement,
            "normed_custom": s.normed_custom,
            "normed": normed[s.id],
        }
        for s in settings
    ]


def _validate(db: Session, req: PersonalSettingIn, exclude_id: Optional[str] = None) -> None:
    if db.get(Employee, req.employee_id) is None:
        raise HTTPException(status_code=422, detail="Сотрудник не найден")
    # 0% не бывает: планировщик отдал бы фазы человеку с потолком дня 0 ч.
    # Пусто — «как обычно».
    if req.involvement is not None and not 0 < req.involvement <= 1:
        raise HTTPException(status_code=422, detail="Вовлечённость — от 1 до 100%")
    if req.normed_custom:
        ids = [n.work_type_id for n in req.normed]
        if len(ids) != len(set(ids)):
            raise HTTPException(status_code=422, detail="Вид работ указан дважды")
        if any(not 0 <= n.percent_of_norm <= 100 for n in req.normed):
            raise HTTPException(
                status_code=422, detail="Процент нормированной работы — от 0 до 100"
            )
        types = {
            w.id: w
            for w in db.query(MandatoryWorkType).filter(MandatoryWorkType.id.in_(ids))
        }
        for wt_id in ids:
            wt = types.get(wt_id)
            if wt is None:
                raise HTTPException(status_code=422, detail="Вид работ не найден")
            if not wt.subtracts_from_pool:
                raise HTTPException(
                    status_code=422,
                    detail=f"Вид работ «{wt.label}» не уменьшает запас на проекты — "
                    "его нельзя задать сотруднику",
                )
        total = sum(n.percent_of_norm for n in req.normed)
        if total > 100 + 1e-9:
            raise HTTPException(
                status_code=422,
                detail=f"Сумма нормированных работ — {total:g}%, больше 100%",
            )
    clash = db.query(EmployeePersonalSetting.id).filter(
        EmployeePersonalSetting.employee_id == req.employee_id,
        EmployeePersonalSetting.effective_year == req.effective_year,
        EmployeePersonalSetting.effective_quarter == req.effective_quarter,
    )
    if exclude_id is not None:
        clash = clash.filter(EmployeePersonalSetting.id != exclude_id)
    if clash.first() is not None:
        raise HTTPException(
            status_code=409, detail="Запись для этого сотрудника и квартала уже есть"
        )


def _apply(db: Session, row: EmployeePersonalSetting, req: PersonalSettingIn) -> None:
    """Записать поля; «по правилам роли» — без своих процентов."""
    row.employee_id = req.employee_id
    row.effective_year = req.effective_year
    row.effective_quarter = req.effective_quarter
    row.involvement = req.involvement
    row.normed_custom = req.normed_custom
    # Старые проценты удаляются до вставки новых: тот же вид упёрся бы в уникальность.
    row.normed.clear()
    db.flush()
    if req.normed_custom:
        row.normed.extend(
            EmployeePersonalNormed(work_type_id=n.work_type_id, percent_of_norm=n.percent_of_norm)
            for n in req.normed
        )


def _get(db: Session, setting_id: str) -> EmployeePersonalSetting:
    row = db.get(EmployeePersonalSetting, setting_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return row


@router.get("", response_model=List[PersonalSettingOut])
def list_settings(team: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Записи сотрудников, состоявших в команде в любые периоды; без команды — все."""
    q = db.query(EmployeePersonalSetting).join(
        Employee, Employee.id == EmployeePersonalSetting.employee_id
    )
    if team is not None:
        q = q.filter(EmployeePersonalSetting.employee_id.in_(list(members_ever(db, [team]))))
    rows = q.order_by(
        Employee.display_name,
        EmployeePersonalSetting.effective_year,
        EmployeePersonalSetting.effective_quarter,
    ).all()
    return _serialize(db, rows)


@router.post("", response_model=PersonalSettingOut, status_code=201)
async def create_setting(
    req: PersonalSettingIn,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    def work() -> dict:
        _validate(db, req)
        row = EmployeePersonalSetting()
        db.add(row)
        _apply(db, row, req)
        db.commit()
        return _serialize(db, [row])[0]

    out = await run_in_threadpool(work)
    await event_bus.publish(_CHANGED)
    return out


@router.put("/{setting_id}", response_model=PersonalSettingOut)
async def update_setting(
    setting_id: str,
    req: PersonalSettingIn,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    def work() -> dict:
        row = _get(db, setting_id)
        _validate(db, req, exclude_id=setting_id)
        _apply(db, row, req)
        db.commit()
        return _serialize(db, [row])[0]

    out = await run_in_threadpool(work)
    await event_bus.publish(_CHANGED)
    return out


@router.delete("/{setting_id}", status_code=204)
async def delete_setting(
    setting_id: str,
    db: Session = Depends(get_db),
    event_bus: EventBroadcaster = Depends(get_event_bus),
):
    def work() -> None:
        db.delete(_get(db, setting_id))
        db.commit()

    await run_in_threadpool(work)
    await event_bus.publish(_CHANGED)
    return None
