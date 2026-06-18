"""Categories API endpoints — CRUD for user-configurable categories."""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.category import Category

router = APIRouter()


# --- Schemas ---

class CategoryResponse(BaseModel):
    id: str
    code: str
    label: str
    color: Optional[str] = None
    sort_order: int = 0
    is_system: bool = False
    work_type_id: Optional[str] = None


class CategoryCreate(BaseModel):
    code: str
    label: str
    color: Optional[str] = None
    sort_order: int = 0
    work_type_id: Optional[str] = None


class CategoryUpdate(BaseModel):
    label: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    work_type_id: Optional[str] = None


# --- Endpoints ---

# Палитра для автоназначения цвета категориям, созданным без явного цвета.
# Подобраны различимые на тёмном фоне дашборда оттенки.
_AUTO_COLOR_PALETTE = [
    "#5b8ff9", "#5ad8a6", "#f6bd16", "#e8684a", "#6dc8ec",
    "#9270ca", "#ff9d4d", "#269a99", "#ff99c3", "#5d7092",
]


def _pick_auto_color(db: Session) -> str:
    """Подобрать цвет для новой категории: первый из палитры, ещё не занятый;
    если все заняты — циклически по числу категорий."""
    used = {row[0] for row in db.query(Category.color).all() if row[0]}
    for color in _AUTO_COLOR_PALETTE:
        if color not in used:
            return color
    total = db.query(Category).count()
    return _AUTO_COLOR_PALETTE[total % len(_AUTO_COLOR_PALETTE)]


def _normalize_color(color: Optional[str]) -> Optional[str]:
    """Привести цвет к виду #RRGGBB.

    Палитра ColorPicker при ненулевой прозрачности отдаёт 8-значный hex
    (#RRGGBBAA). Колонка хранит только #RRGGBB; на Postgres лишние символы
    приводят к ошибке длины (SQLite её игнорирует). Прозрачность приложению
    не нужна — отбрасываем.
    """
    if not color:
        return color
    c = color.strip()
    if c.startswith("#") and len(c) > 7:
        c = c[:7]
    return c


def _validate_work_type_id(db: Session, work_type_id: Optional[str]) -> None:
    """Raise 422 if work_type_id is set but unknown or inactive."""
    if work_type_id is None:
        return
    from app.models import MandatoryWorkType
    wt = (
        db.query(MandatoryWorkType)
        .filter(MandatoryWorkType.id == work_type_id)
        .one_or_none()
    )
    if wt is None:
        raise HTTPException(status_code=422, detail=f"Unknown work_type_id {work_type_id!r}")
    if not wt.is_active:
        raise HTTPException(status_code=422, detail=f"Work type {wt.code!r} is not active")


@router.get("", response_model=List[CategoryResponse])
async def list_categories(db: Session = Depends(get_db)):
    """Список всех категорий."""
    cats = db.query(Category).order_by(Category.sort_order, Category.code).all()
    return [
        CategoryResponse(
            id=c.id, code=c.code, label=c.label,
            color=c.color, sort_order=c.sort_order, is_system=c.is_system,
            work_type_id=c.work_type_id,
        )
        for c in cats
    ]


@router.post("", response_model=CategoryResponse, status_code=201)
async def create_category(body: CategoryCreate, db: Session = Depends(get_db)):
    """Создать категорию."""
    existing = db.query(Category).filter(Category.code == body.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Категория с кодом '{body.code}' уже существует")

    _validate_work_type_id(db, body.work_type_id)

    cat = Category(
        code=body.code,
        label=body.label,
        color=_normalize_color(body.color) or _pick_auto_color(db),
        sort_order=body.sort_order,
        work_type_id=body.work_type_id,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return CategoryResponse(
        id=cat.id, code=cat.code, label=cat.label,
        color=cat.color, sort_order=cat.sort_order, is_system=cat.is_system,
        work_type_id=cat.work_type_id,
    )


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: str, body: CategoryUpdate, db: Session = Depends(get_db)):
    """Обновить категорию."""
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")

    data = body.model_dump(exclude_unset=True)
    if "work_type_id" in data:
        _validate_work_type_id(db, data["work_type_id"])

    if body.label is not None:
        cat.label = body.label
    if body.color is not None:
        cat.color = _normalize_color(body.color)
    if body.sort_order is not None:
        cat.sort_order = body.sort_order
    if "work_type_id" in data:
        cat.work_type_id = data["work_type_id"]
    db.commit()
    db.refresh(cat)
    return CategoryResponse(
        id=cat.id, code=cat.code, label=cat.label,
        color=cat.color, sort_order=cat.sort_order, is_system=cat.is_system,
        work_type_id=cat.work_type_id,
    )


@router.delete("/{category_id}")
async def delete_category(category_id: str, db: Session = Depends(get_db)):
    """Удалить категорию (системные нельзя)."""
    cat = db.get(Category, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Категория не найдена")
    if cat.is_system:
        raise HTTPException(status_code=400, detail="Системную категорию нельзя удалить")
    db.delete(cat)
    db.commit()
    return {"ok": True}
