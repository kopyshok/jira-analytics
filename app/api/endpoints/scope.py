"""Scope configuration API endpoints.

Управление областью загрузки данных из Jira:
- scope_projects: какие проекты Jira разрешены для загрузки
- scope_roots: корневые эпики/задачи для авто-раскладки по категориям
- category_overrides: точечные переопределения категорий
"""

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ScopeProject, ScopeRoot, CategoryOverride
from app.repositories.base import BaseRepository


router = APIRouter()


# === Request/Response schemas ===

class ScopeProjectCreate(BaseModel):
    jira_project_key: str
    jira_project_id: Optional[str] = None
    is_enabled: bool = True


class ScopeProjectBatchRequest(BaseModel):
    """Batch-добавление/удаление проектов из scope."""
    add: List[str] = []
    remove: List[str] = []


class ScopeProjectBatchResponse(BaseModel):
    added: int = 0
    removed: int = 0


class ScopeProjectResponse(BaseModel):
    id: str
    jira_project_key: str
    jira_project_id: Optional[str] = None
    is_enabled: bool

    class Config:
        from_attributes = True


class ScopeRootCreate(BaseModel):
    category_code: str
    jira_issue_key: str
    jira_issue_id: Optional[str] = None
    project_key: Optional[str] = None
    is_enabled: bool = True


class ScopeRootResponse(BaseModel):
    id: str
    category_code: str
    jira_issue_key: str
    jira_issue_id: Optional[str] = None
    project_key: Optional[str] = None
    is_enabled: bool

    class Config:
        from_attributes = True


class CategoryOverrideCreate(BaseModel):
    jira_issue_key: str
    category_code: str
    comment: Optional[str] = None


class CategoryOverrideResponse(BaseModel):
    id: str
    jira_issue_key: str
    category_code: str
    comment: Optional[str] = None

    class Config:
        from_attributes = True


# === Scope Projects ===

@router.get("/projects", response_model=List[ScopeProjectResponse])
async def list_scope_projects(db: Session = Depends(get_db)):
    """Список разрешённых проектов Jira для загрузки."""
    repo = BaseRepository(ScopeProject, db)
    return repo.get_all(limit=1000)


@router.post("/projects", response_model=ScopeProjectResponse, status_code=201)
async def add_scope_project(
    data: ScopeProjectCreate,
    db: Session = Depends(get_db),
):
    """Добавить проект Jira в область загрузки."""
    repo = BaseRepository(ScopeProject, db)

    existing = repo.get_by_field("jira_project_key", data.jira_project_key)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Project {data.jira_project_key} already in scope",
        )

    project = repo.create(data.model_dump())
    db.commit()
    return project


@router.post("/projects/batch", response_model=ScopeProjectBatchResponse)
async def batch_scope_projects(
    data: ScopeProjectBatchRequest,
    db: Session = Depends(get_db),
):
    """Добавить и/или удалить несколько проектов за один запрос."""
    repo = BaseRepository(ScopeProject, db)
    added = 0
    removed = 0

    for key in data.add:
        if not repo.get_by_field("jira_project_key", key):
            repo.create({"jira_project_key": key, "is_enabled": True})
            added += 1

    for key in data.remove:
        existing = repo.get_by_field("jira_project_key", key)
        if existing:
            repo.delete(existing)
            removed += 1

    db.commit()
    return ScopeProjectBatchResponse(added=added, removed=removed)


@router.delete("/projects/{project_key}")
async def remove_scope_project(
    project_key: str,
    db: Session = Depends(get_db),
):
    """Удалить проект из области загрузки."""
    repo = BaseRepository(ScopeProject, db)
    existing = repo.get_by_field("jira_project_key", project_key)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found in scope")

    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "project_key": project_key}


# === Scope Roots ===

@router.get("/roots", response_model=List[ScopeRootResponse])
async def list_scope_roots(
    category_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Список корневых эпиков/задач для авто-раскладки по категориям."""
    repo = BaseRepository(ScopeRoot, db)
    roots = repo.get_all(limit=1000)
    if category_code:
        roots = [r for r in roots if r.category_code == category_code]
    return roots


@router.post("/roots", response_model=ScopeRootResponse, status_code=201)
async def add_scope_root(
    data: ScopeRootCreate,
    db: Session = Depends(get_db),
):
    """Добавить корневой эпик/задачу для категории."""
    repo = BaseRepository(ScopeRoot, db)
    root = repo.create(data.model_dump())
    db.commit()
    return root


@router.delete("/roots/{root_id}")
async def remove_scope_root(
    root_id: str,
    db: Session = Depends(get_db),
):
    """Удалить корневой эпик/задачу из scope."""
    repo = BaseRepository(ScopeRoot, db)
    existing = repo.get(root_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Scope root not found")

    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "id": root_id}


# === Category Overrides ===

@router.get("/overrides", response_model=List[CategoryOverrideResponse])
async def list_category_overrides(db: Session = Depends(get_db)):
    """Список точечных переопределений категорий."""
    repo = BaseRepository(CategoryOverride, db)
    return repo.get_all(limit=1000)


@router.post("/overrides", response_model=CategoryOverrideResponse, status_code=201)
async def add_category_override(
    data: CategoryOverrideCreate,
    db: Session = Depends(get_db),
):
    """Добавить переопределение категории для задачи."""
    repo = BaseRepository(CategoryOverride, db)

    existing = repo.get_by_field("jira_issue_key", data.jira_issue_key)
    if existing:
        # Update existing override
        updated = repo.update(existing, data.model_dump())
        db.commit()
        return updated

    override = repo.create(data.model_dump())
    db.commit()
    return override


@router.delete("/overrides/{issue_key}")
async def remove_category_override(
    issue_key: str,
    db: Session = Depends(get_db),
):
    """Удалить переопределение категории."""
    repo = BaseRepository(CategoryOverride, db)
    existing = repo.get_by_field("jira_issue_key", issue_key)
    if not existing:
        raise HTTPException(status_code=404, detail="Override not found")

    repo.delete(existing)
    db.commit()
    return {"status": "deleted", "issue_key": issue_key}
