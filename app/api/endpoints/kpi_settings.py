"""Справочники раздела KPI: метрики, профили оценки, нормативы Cycle Time, общие правила.

Все маршруты — только для администратора (регистрируются с ``_admin_dep`` в
``app/api/router.py``). Словарь допустимых атрибутов условий отдаётся из
``app.services.kpi.conditions`` — единственного места, где он определён,
чтобы интерфейс настроек и движок расчёта не расходились.
"""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.app_setting import AppSetting
from app.models.issue import Issue
from app.models.kpi import KpiCycleTimeNorm, KpiMetric, KpiProfile, KpiProfileMetric
from app.models.project import Project
from app.services.kpi.conditions import (
    ATTRIBUTE_CHOICES,
    FILLABLE_FIELDS,
    PERIOD_WINDOWS,
    PERSON_FIELDS,
    ConditionSet,
)
from app.services.kpi.settings import KpiSettings, read_kpi_settings

router = APIRouter()

_WEIGHT_TOLERANCE = 0.001
_EMPTY_POLICIES = {"redistribute", "full", "zero"}


# === Schemas ===

class KpiConditionSchema(BaseModel):
    attr: str
    op: str
    value: object = None


class KpiConditionSetSchema(BaseModel):
    unit: str = "issues"
    person_field: str = "author"
    period_window: str = "closed_in"
    conditions: List[KpiConditionSchema] = []


class KpiMetricIn(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    calc_kind: str
    numerator: KpiConditionSetSchema
    denominator: Optional[KpiConditionSetSchema] = None
    fact_field: Optional[str] = None
    score_fields: Optional[List[str]] = None
    score_max: Optional[float] = None
    invert: bool = False
    cap_at_100: bool = True
    sort_order: int = 0


class KpiMetricOut(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    calc_kind: str
    numerator: KpiConditionSetSchema
    denominator: Optional[KpiConditionSetSchema] = None
    fact_field: Optional[str] = None
    score_fields: Optional[List[str]] = None
    score_max: Optional[float] = None
    invert: bool
    cap_at_100: bool
    is_builtin: bool
    sort_order: int


class KpiProfileMetricIn(BaseModel):
    metric_code: str
    weight: float
    sort_order: int = 0


class KpiProfileMetricOut(BaseModel):
    metric_code: str
    metric_name: str
    weight: float
    sort_order: int


class KpiProfileIn(BaseModel):
    code: str
    name: str
    role_code: Optional[str] = None
    target_pct: float = 80.0
    warn_band_pct: float = 10.0
    is_enabled: bool = True
    metrics: List[KpiProfileMetricIn] = []


class KpiProfileOut(BaseModel):
    id: str
    code: str
    name: str
    role_code: Optional[str] = None
    target_pct: float
    warn_band_pct: float
    is_enabled: bool
    metrics: List[KpiProfileMetricOut]


class KpiNormIn(BaseModel):
    team: str
    year: int
    quarter: int
    norm_value: float


class KpiNormOut(BaseModel):
    id: str
    team: str
    year: int
    quarter: int
    norm_value: float

    class Config:
        from_attributes = True


class KpiGeneralSettings(BaseModel):
    excluded_statuses: List[str]
    worklog_deadline_days: int
    worklog_deadline_time: str
    empty_policy: str


# === Helpers ===

def _condition_set_to_json(cs: KpiConditionSetSchema) -> str:
    return json.dumps(cs.model_dump(), ensure_ascii=False)


def _condition_set_from_json(raw: Optional[str]) -> KpiConditionSetSchema:
    if not raw:
        return KpiConditionSetSchema()
    return KpiConditionSetSchema(**json.loads(raw))


def _metric_to_out(m: KpiMetric) -> KpiMetricOut:
    return KpiMetricOut(
        id=m.id, code=m.code, name=m.name, description=m.description, calc_kind=m.calc_kind,
        numerator=_condition_set_from_json(m.numerator_json),
        denominator=_condition_set_from_json(m.denominator_json) if m.denominator_json else None,
        fact_field=m.fact_field,
        score_fields=json.loads(m.score_fields) if m.score_fields else None,
        score_max=m.score_max, invert=m.invert, cap_at_100=m.cap_at_100,
        is_builtin=m.is_builtin, sort_order=m.sort_order,
    )


def _apply_metric_fields(metric: KpiMetric, body: KpiMetricIn) -> None:
    numerator_json = _condition_set_to_json(body.numerator)
    denominator_json = _condition_set_to_json(body.denominator) if body.denominator else None
    # Опечатка в атрибуте/сравнении/признаке «кто считается» должна провалить
    # сохранение метрики понятной ошибкой (ConditionError → 422, см.
    # app/main.py), а не тихо лечь в базу и ослабить фильтр расчёта.
    ConditionSet.from_json(numerator_json)
    if denominator_json:
        ConditionSet.from_json(denominator_json)

    metric.code = body.code
    metric.name = body.name
    metric.description = body.description
    metric.calc_kind = body.calc_kind
    metric.numerator_json = numerator_json
    metric.denominator_json = denominator_json
    metric.fact_field = body.fact_field
    metric.score_fields = json.dumps(body.score_fields, ensure_ascii=False) if body.score_fields else None
    metric.score_max = body.score_max
    metric.invert = body.invert
    metric.cap_at_100 = body.cap_at_100
    metric.sort_order = body.sort_order


def _profile_to_out(p: KpiProfile) -> KpiProfileOut:
    return KpiProfileOut(
        id=p.id, code=p.code, name=p.name, role_code=p.role_code,
        target_pct=p.target_pct, warn_band_pct=p.warn_band_pct, is_enabled=p.is_enabled,
        metrics=[
            KpiProfileMetricOut(
                metric_code=link.metric.code, metric_name=link.metric.name,
                weight=link.weight, sort_order=link.sort_order,
            )
            for link in sorted(p.metrics, key=lambda link: link.sort_order)
        ],
    )


def _validate_weight_sum(metrics: List[KpiProfileMetricIn]) -> None:
    """Сумма весов профиля обязана равняться единице (см. спека, раздел 6)."""
    total = sum(m.weight for m in metrics)
    if abs(total - 1.0) > _WEIGHT_TOLERANCE:
        raise HTTPException(
            status_code=422,
            detail=f"Сумма весов профиля должна быть равна 100% — сейчас {round(total * 100, 1)}%",
        )


def _resolve_metrics_by_code(db: Session, codes: List[str]) -> dict[str, KpiMetric]:
    if not codes:
        return {}
    rows = db.query(KpiMetric).filter(KpiMetric.code.in_(codes)).all()
    found = {m.code: m for m in rows}
    missing = [c for c in codes if c not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Неизвестные метрики: {', '.join(missing)}")
    return found


def _set_kpi_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _general_from_settings(s: KpiSettings) -> KpiGeneralSettings:
    return KpiGeneralSettings(
        excluded_statuses=s.excluded_statuses,
        worklog_deadline_days=s.worklog_deadline_days,
        worklog_deadline_time=s.worklog_deadline_time,
        empty_policy=s.empty_policy,
    )


# === Метрики ===

@router.get("/metrics", response_model=List[KpiMetricOut])
def list_metrics(db: Session = Depends(get_db)):
    rows = db.query(KpiMetric).order_by(KpiMetric.sort_order, KpiMetric.name).all()
    return [_metric_to_out(m) for m in rows]


@router.post("/metrics", response_model=KpiMetricOut, status_code=201)
def create_metric(body: KpiMetricIn, db: Session = Depends(get_db)):
    if db.query(KpiMetric).filter(KpiMetric.code == body.code).first():
        raise HTTPException(status_code=409, detail=f"Метрика с кодом {body.code!r} уже существует")
    metric = KpiMetric(is_builtin=False)
    _apply_metric_fields(metric, body)
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return _metric_to_out(metric)


@router.put("/metrics/{metric_id}", response_model=KpiMetricOut)
def update_metric(metric_id: str, body: KpiMetricIn, db: Session = Depends(get_db)):
    metric = db.get(KpiMetric, metric_id)
    if metric is None:
        raise HTTPException(status_code=404, detail="Метрика не найдена")
    if body.code != metric.code and db.query(KpiMetric).filter(KpiMetric.code == body.code).first():
        raise HTTPException(status_code=409, detail=f"Метрика с кодом {body.code!r} уже существует")
    _apply_metric_fields(metric, body)
    db.commit()
    db.refresh(metric)
    return _metric_to_out(metric)


@router.delete("/metrics/{metric_id}")
def delete_metric(metric_id: str, db: Session = Depends(get_db)):
    metric = db.get(KpiMetric, metric_id)
    if metric is None:
        raise HTTPException(status_code=404, detail="Метрика не найдена")
    in_use = db.query(KpiProfileMetric).filter(KpiProfileMetric.metric_id == metric_id).count()
    if in_use > 0:
        raise HTTPException(status_code=409, detail=f"Метрика используется в {in_use} профилях")
    db.delete(metric)
    db.commit()
    return {"status": "deleted"}


# === Профили оценки ===

@router.get("/profiles", response_model=List[KpiProfileOut])
def list_profiles(db: Session = Depends(get_db)):
    rows = db.query(KpiProfile).order_by(KpiProfile.name).all()
    return [_profile_to_out(p) for p in rows]


@router.post("/profiles", response_model=KpiProfileOut, status_code=201)
def create_profile(body: KpiProfileIn, db: Session = Depends(get_db)):
    _validate_weight_sum(body.metrics)
    if db.query(KpiProfile).filter(KpiProfile.code == body.code).first():
        raise HTTPException(status_code=409, detail=f"Профиль с кодом {body.code!r} уже существует")
    metrics_by_code = _resolve_metrics_by_code(db, [m.metric_code for m in body.metrics])

    profile = KpiProfile(
        code=body.code, name=body.name, role_code=body.role_code,
        target_pct=body.target_pct, warn_band_pct=body.warn_band_pct, is_enabled=body.is_enabled,
    )
    db.add(profile)
    db.flush()
    for m in body.metrics:
        db.add(KpiProfileMetric(
            profile_id=profile.id, metric_id=metrics_by_code[m.metric_code].id,
            weight=m.weight, sort_order=m.sort_order,
        ))
    db.commit()
    db.refresh(profile)
    return _profile_to_out(profile)


@router.put("/profiles/{profile_id}", response_model=KpiProfileOut)
def update_profile(profile_id: str, body: KpiProfileIn, db: Session = Depends(get_db)):
    _validate_weight_sum(body.metrics)
    profile = db.get(KpiProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    if body.code != profile.code and db.query(KpiProfile).filter(KpiProfile.code == body.code).first():
        raise HTTPException(status_code=409, detail=f"Профиль с кодом {body.code!r} уже существует")
    metrics_by_code = _resolve_metrics_by_code(db, [m.metric_code for m in body.metrics])

    profile.code = body.code
    profile.name = body.name
    profile.role_code = body.role_code
    profile.target_pct = body.target_pct
    profile.warn_band_pct = body.warn_band_pct
    profile.is_enabled = body.is_enabled

    db.query(KpiProfileMetric).filter(KpiProfileMetric.profile_id == profile.id).delete()
    db.flush()
    for m in body.metrics:
        db.add(KpiProfileMetric(
            profile_id=profile.id, metric_id=metrics_by_code[m.metric_code].id,
            weight=m.weight, sort_order=m.sort_order,
        ))
    db.commit()
    db.refresh(profile)
    return _profile_to_out(profile)


@router.delete("/profiles/{profile_id}")
def delete_profile(profile_id: str, db: Session = Depends(get_db)):
    profile = db.get(KpiProfile, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Профиль не найден")
    db.delete(profile)
    db.commit()
    return {"status": "deleted"}


# === Нормативы Cycle Time ===

@router.get("/norms", response_model=List[KpiNormOut])
def list_norms(
    year: Optional[int] = Query(None),
    quarter: Optional[int] = Query(None, ge=1, le=4),
    db: Session = Depends(get_db),
):
    q = db.query(KpiCycleTimeNorm)
    if year is not None:
        q = q.filter(KpiCycleTimeNorm.year == year)
    if quarter is not None:
        q = q.filter(KpiCycleTimeNorm.quarter == quarter)
    return q.order_by(KpiCycleTimeNorm.team, KpiCycleTimeNorm.year, KpiCycleTimeNorm.quarter).all()


@router.put("/norms", response_model=List[KpiNormOut])
def save_norms(body: List[KpiNormIn], db: Session = Depends(get_db)):
    """Обновить нормативы: существующие пары команда/год/квартал — на месте, недостающие — создать."""
    result = []
    for item in body:
        row = (
            db.query(KpiCycleTimeNorm)
            .filter_by(team=item.team, year=item.year, quarter=item.quarter)
            .first()
        )
        if row is None:
            row = KpiCycleTimeNorm(
                team=item.team, year=item.year, quarter=item.quarter, norm_value=item.norm_value,
            )
            db.add(row)
        else:
            row.norm_value = item.norm_value
        result.append(row)
    db.commit()
    for row in result:
        db.refresh(row)
    return result


# === Общие правила ===

@router.get("/general", response_model=KpiGeneralSettings)
def get_general(db: Session = Depends(get_db)):
    return _general_from_settings(read_kpi_settings(db))


@router.put("/general", response_model=KpiGeneralSettings)
def save_general(body: KpiGeneralSettings, db: Session = Depends(get_db)):
    if body.empty_policy not in _EMPTY_POLICIES:
        raise HTTPException(status_code=422, detail="Недопустимая политика при отсутствии данных")
    if body.worklog_deadline_days < 1:
        raise HTTPException(
            status_code=422,
            detail="Срок внесения трудозатрат должен быть не меньше одного рабочего дня",
        )
    _set_kpi_setting(db, "kpi_excluded_statuses", json.dumps(body.excluded_statuses, ensure_ascii=False))
    _set_kpi_setting(db, "kpi_worklog_deadline_days", str(body.worklog_deadline_days))
    _set_kpi_setting(db, "kpi_worklog_deadline_time", body.worklog_deadline_time)
    _set_kpi_setting(db, "kpi_empty_policy", body.empty_policy)
    db.commit()
    return _general_from_settings(read_kpi_settings(db))


# === Словарь атрибутов условий ===

_ATTR_VALUE_SOURCES = {
    "issue_type": Issue.issue_type,
    "subtype": Issue.subtype,
    "status": Issue.status,
    "resolution": Issue.resolution,
    "environment": Issue.environment,
    "cost_type": Issue.cost_type,
    "direction": Issue.direction,
}


@router.get("/attributes")
def get_attributes(db: Session = Depends(get_db)) -> dict:
    """Словарь допустимых атрибутов условий для конструктора метрики в настройках."""
    attrs = []
    for choice in ATTRIBUTE_CHOICES:
        item = dict(choice)
        key = choice["key"]
        if key == "project_key":
            item["choices"] = sorted(
                v for (v,) in db.query(Project.key).distinct().all() if v
            )
        elif key == "field_filled":
            item["choices"] = list(FILLABLE_FIELDS.keys())
        elif key in _ATTR_VALUE_SOURCES:
            column = _ATTR_VALUE_SOURCES[key]
            item["choices"] = sorted(v for (v,) in db.query(column).distinct().all() if v)
        attrs.append(item)
    return {
        "attributes": attrs,
        "person_fields": sorted(PERSON_FIELDS),
        "period_windows": sorted(PERIOD_WINDOWS),
    }
