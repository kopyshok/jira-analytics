"""Work-type thematic report API."""
import asyncio
import json
from contextlib import suppress
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth_deps import get_current_user
from app.models.user import User
from app.models.work_type_report_snapshot import WorkTypeReportSnapshot
from app.models.work_type_report_layout import WorkTypeReportLayout
from app.models.mandatory_work_type import MandatoryWorkType
from app.models.issue_classification import IssueClassification
from app.schemas.work_type_report import (
    WorkTypeReportRequest, WorkTypeReportResponse,
    CandidateAcceptRequest, CandidateMergeRequest, CandidateIgnoreRequest,
    ManualClassifyRequest,
    LayoutCreateRequest, LayoutUpdateRequest, LayoutOut,
    AliasAddRequest, ThemeAliasResponse,
    ThresholdRequest, ThresholdResponse,
)
from app.services.work_type_report_service import (
    WorkTypeReportService,
    DEFAULT_EMBEDDING_THRESHOLD,
    THRESHOLD_SETTING_KEY,
)
from app.services.theme_dictionary_service import ThemeDictionaryService
from app.services.llm.base import get_llm_provider
from app.services.work_type_report_xlsx import export_snapshot_to_xlsx


router = APIRouter()


def _to_response(snap: WorkTypeReportSnapshot, wt: MandatoryWorkType) -> WorkTypeReportResponse:
    is_stale = snap.dictionary_version != wt.theme_dict_version
    return WorkTypeReportResponse(
        snapshot_id=snap.id,
        work_type_id=snap.work_type_id,
        year=snap.year, quarter=snap.quarter, month=snap.month,
        start_date=snap.start_date, end_date=snap.end_date,
        team_set=json.loads(snap.team_set_json),
        generated_at=snap.generated_at,
        model_id=snap.model_id, prompt_version=snap.prompt_version,
        dictionary_version=snap.dictionary_version,
        is_stale=is_stale,
        data=json.loads(snap.snapshot_data),
    )


def _make_service(db: Session) -> WorkTypeReportService:
    """Construct service with the configured LLM provider for both phases."""
    try:
        provider = get_llm_provider(db)
    except Exception:
        provider = None
    return WorkTypeReportService(
        db, classifier_provider=provider, synthesizer_provider=provider,
    )


@router.post("", response_model=WorkTypeReportResponse)
async def build_report(
    payload: WorkTypeReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build (or rebuild on force_refresh) a thematic report snapshot."""
    wt = db.get(MandatoryWorkType, payload.work_type_id)
    if not wt:
        raise HTTPException(404, "Work type not found")
    svc = _make_service(db)
    snap = await svc.get_or_build(
        work_type_id=payload.work_type_id,
        year=payload.year, quarter=payload.quarter, month=payload.month,
        teams=payload.teams, force_refresh=payload.force_refresh,
        user_id=current_user.id,
    )
    return _to_response(snap, wt)


def _disconnect_checker(request: Request):
    """Возвращает async-коллбек, который возвращает True если клиент отключился."""
    async def _check() -> bool:
        return await request.is_disconnected()
    return _check


@router.post("/build/stream")
async def build_report_stream(
    payload: WorkTypeReportRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SSE-стрим прогресса построения тематического отчёта.

    Возвращает ``text/event-stream`` с событиями:
    - ``phase_start`` — вход в фазу (scope/map/cluster/reduce/save)
    - ``progress`` — прогресс внутри Map-фазы (per-issue)
    - ``phase_done`` — фаза завершена
    - ``done`` — snapshot сохранён, полные данные
    - ``error`` — ошибка бэкенда
    - ``cancelled`` — клиент отключился
    """
    wt = db.get(MandatoryWorkType, payload.work_type_id)
    if not wt:
        raise HTTPException(404, "Work type not found")

    async def event_gen():
        queue: asyncio.Queue = asyncio.Queue()

        async def on_progress(event: dict) -> None:
            await queue.put(event)

        async def run() -> None:
            try:
                svc = _make_service(db)
                snap = await svc.get_or_build(
                    work_type_id=payload.work_type_id,
                    year=payload.year,
                    quarter=payload.quarter,
                    month=payload.month,
                    teams=payload.teams,
                    force_refresh=payload.force_refresh,
                    user_id=current_user.id,
                    on_progress=on_progress,
                    cancel_check=_disconnect_checker(http_request),
                )
                await queue.put({
                    "type": "done",
                    "snapshot_id": snap.id,
                    "work_type_id": snap.work_type_id,
                    "year": snap.year,
                    "quarter": snap.quarter,
                    "month": snap.month,
                    "totals": json.loads(snap.snapshot_data).get("totals", {}),
                })
            except asyncio.CancelledError:
                await queue.put({"type": "cancelled", "reason": "client disconnected"})
                raise
            except Exception as e:
                await queue.put({"type": "error", "detail": str(e)})

        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")
                if event["type"] in ("done", "error", "cancelled"):
                    break
        finally:
            if not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@router.get("", response_model=WorkTypeReportResponse)
async def get_report(
    work_type_id: str = Query(...),
    year: int = Query(..., ge=2020, le=2100),
    quarter: int = Query(..., ge=1, le=4),
    month: Optional[int] = Query(None, ge=1, le=12),
    teams: Optional[str] = Query(None, description="CSV"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wt = db.get(MandatoryWorkType, work_type_id)
    if not wt:
        raise HTTPException(404, "Work type not found")
    team_list = [t.strip() for t in teams.split(",") if t.strip()] if teams else []
    svc = _make_service(db)
    snap = await svc.get_or_build(
        work_type_id=work_type_id, year=year, quarter=quarter, month=month,
        teams=team_list, force_refresh=False, user_id=current_user.id,
    )
    return _to_response(snap, wt)


@router.post("/candidates/accept")
def accept_candidate(
    payload: CandidateAcceptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Accept a candidate from a snapshot — creates Theme + reassigns matching classifications.

    Soft re-aggregate: snapshot пересобирается без LLM, поэтому возврат на страницу мгновенный.
    """
    snap = db.get(WorkTypeReportSnapshot, payload.snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    name = payload.new_theme_name or payload.proposed_name
    svc = ThemeDictionaryService(db)
    try:
        theme = svc.create_theme(
            work_type_id=snap.work_type_id, name=name, color=payload.color,
            created_by=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.execute(
        update(IssueClassification)
        .where(
            IssueClassification.work_type_id == snap.work_type_id,
            IssueClassification.candidate_name == payload.proposed_name,
            IssueClassification.theme_id.is_(None),
        )
        .values(theme_id=theme.id, candidate_name=None)
    )
    db.commit()
    _make_service(db).rebuild_aggregates(snap)
    return {"ok": True, "theme_id": theme.id}


@router.post("/candidates/merge")
def merge_candidate(
    payload: CandidateMergeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Merge a candidate into an existing theme.

    Помимо перепривязки классификаций, `proposed_name` записывается в
    `Theme.aliases` целевой темы — это обучает embedding-матчер: следующие
    задачи с похожей формулировкой попадут в эту тему автоматически.
    Recompute centroid темы запускается в ThemeDictionaryService.add_alias.
    """
    snap = db.get(WorkTypeReportSnapshot, payload.snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    db.execute(
        update(IssueClassification)
        .where(
            IssueClassification.work_type_id == snap.work_type_id,
            IssueClassification.candidate_name == payload.proposed_name,
            IssueClassification.theme_id.is_(None),
        )
        .values(theme_id=payload.target_theme_id, candidate_name=None)
    )
    db.commit()

    svc = ThemeDictionaryService(db)
    try:
        svc.add_alias(payload.target_theme_id, payload.proposed_name)
    except ValueError:
        pass  # тему могли удалить между запросами — игнорим, классификации уже перепривязаны

    _make_service(db).rebuild_aggregates(snap)
    return {"ok": True}


@router.post("/themes/{theme_id}/aliases", response_model=ThemeAliasResponse)
def add_theme_alias(
    theme_id: str,
    payload: AliasAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.add_alias(theme_id, payload.alias)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeAliasResponse(theme_id=t.id, aliases=t.aliases)


@router.delete("/themes/{theme_id}/aliases", response_model=ThemeAliasResponse)
def delete_theme_alias(
    theme_id: str,
    alias: str = Query(..., min_length=1, max_length=255),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ThemeDictionaryService(db)
    try:
        t = svc.remove_alias(theme_id, alias)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return ThemeAliasResponse(theme_id=t.id, aliases=t.aliases)


@router.get("/settings/embedding-threshold", response_model=ThresholdResponse)
def get_embedding_threshold_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.api.endpoints.settings import _get_setting
    raw = _get_setting(db, THRESHOLD_SETTING_KEY)
    try:
        value = float(raw) if raw else DEFAULT_EMBEDDING_THRESHOLD
    except (TypeError, ValueError):
        value = DEFAULT_EMBEDDING_THRESHOLD
    return ThresholdResponse(threshold=value)


@router.put("/settings/embedding-threshold", response_model=ThresholdResponse)
def set_embedding_threshold(
    payload: ThresholdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.api.endpoints.settings import _set_setting
    _set_setting(db, THRESHOLD_SETTING_KEY, str(payload.threshold))
    db.commit()
    return ThresholdResponse(threshold=payload.threshold)


@router.post("/candidates/ignore")
def ignore_candidate(
    payload: CandidateIgnoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Скрыть кандидата: классификациям обнуляется candidate_name → попадают в «Другое».

    Soft re-aggregate без LLM. Если LLM при следующем full-rebuild снова сгенерирует
    то же имя — кандидат вернётся; для постоянного скрытия используйте «Слить с» с
    подходящей темой.
    """
    snap = db.get(WorkTypeReportSnapshot, payload.snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    db.execute(
        update(IssueClassification)
        .where(
            IssueClassification.work_type_id == snap.work_type_id,
            IssueClassification.candidate_name == payload.proposed_name,
            IssueClassification.theme_id.is_(None),
        )
        .values(candidate_name=None)
    )
    db.commit()
    _make_service(db).rebuild_aggregates(snap)
    return {"ok": True}


@router.post("/manual-classify")
def manual_classify(
    payload: ManualClassifyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set theme_id on a single classification — overrides AI."""
    cls = db.execute(
        select(IssueClassification).where(
            IssueClassification.issue_id == payload.issue_id,
            IssueClassification.work_type_id == payload.work_type_id,
        )
    ).scalar_one_or_none()
    if cls:
        cls.theme_id = payload.theme_id
        cls.failed = False
        cls.failure_reason = None
        cls.llm_confidence = 1.0
        cls.prompt_version = "manual"
        if payload.contribution_text is not None:
            cls.contribution_text = payload.contribution_text
        cls.candidate_name = None
        cls.updated_at = datetime.utcnow()
    else:
        # Create one (rare — implementer picked a brand-new (issue, work_type) pairing)
        wt = db.get(MandatoryWorkType, payload.work_type_id)
        cls = IssueClassification(
            issue_id=payload.issue_id, work_type_id=payload.work_type_id,
            theme_id=payload.theme_id,
            contribution_text=payload.contribution_text,
            input_hash="manual",
            dictionary_version=(wt.theme_dict_version if wt else 1),
            llm_confidence=1.0,
            prompt_version="manual",
        )
        db.add(cls)
    db.commit()
    return {"ok": True}


# ---- Layouts ----

@router.get("/layouts", response_model=list[LayoutOut])
def list_layouts(
    work_type_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = db.execute(
        select(WorkTypeReportLayout).where(
            WorkTypeReportLayout.user_id == current_user.id,
            WorkTypeReportLayout.work_type_id == work_type_id,
        ).order_by(WorkTypeReportLayout.is_default.desc(), WorkTypeReportLayout.name)
    ).scalars().all()
    return [_layout_to_out(r) for r in rows]


def _layout_to_out(row: WorkTypeReportLayout) -> LayoutOut:
    return LayoutOut(
        id=row.id, user_id=row.user_id, work_type_id=row.work_type_id,
        name=row.name,
        grouping_dims=json.loads(row.grouping_dims_json),
        visible_columns=json.loads(row.visible_columns_json) if row.visible_columns_json else None,
        is_default=row.is_default,
        created_at=row.created_at, updated_at=row.updated_at,
    )


@router.post("/layouts", response_model=LayoutOut, status_code=201)
def create_layout(
    payload: LayoutCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.is_default:
        # Clear other defaults for this user×work_type
        db.execute(
            update(WorkTypeReportLayout)
            .where(
                WorkTypeReportLayout.user_id == current_user.id,
                WorkTypeReportLayout.work_type_id == payload.work_type_id,
                WorkTypeReportLayout.is_default.is_(True),
            )
            .values(is_default=False)
        )
    row = WorkTypeReportLayout(
        user_id=current_user.id, work_type_id=payload.work_type_id,
        name=payload.name,
        grouping_dims_json=json.dumps(payload.grouping_dims, ensure_ascii=False),
        visible_columns_json=json.dumps(payload.visible_columns, ensure_ascii=False) if payload.visible_columns else None,
        is_default=payload.is_default,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _layout_to_out(row)


@router.patch("/layouts/{layout_id}", response_model=LayoutOut)
def update_layout(
    layout_id: str,
    payload: LayoutUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.get(WorkTypeReportLayout, layout_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(404, "Layout not found")
    if payload.name is not None:
        row.name = payload.name
    if payload.grouping_dims is not None:
        row.grouping_dims_json = json.dumps(payload.grouping_dims, ensure_ascii=False)
    if payload.visible_columns is not None:
        row.visible_columns_json = json.dumps(payload.visible_columns, ensure_ascii=False)
    if payload.is_default is True:
        # Clear other defaults
        db.execute(
            update(WorkTypeReportLayout)
            .where(
                WorkTypeReportLayout.user_id == current_user.id,
                WorkTypeReportLayout.work_type_id == row.work_type_id,
                WorkTypeReportLayout.is_default.is_(True),
                WorkTypeReportLayout.id != row.id,
            )
            .values(is_default=False)
        )
        row.is_default = True
    elif payload.is_default is False:
        row.is_default = False
    db.commit()
    db.refresh(row)
    return _layout_to_out(row)


@router.delete("/layouts/{layout_id}")
def delete_layout(
    layout_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.get(WorkTypeReportLayout, layout_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(404, "Layout not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/export/{snapshot_id}.xlsx")
def export_xlsx(
    snapshot_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    snap = db.get(WorkTypeReportSnapshot, snapshot_id)
    if not snap:
        raise HTTPException(404, "Snapshot not found")
    blob = export_snapshot_to_xlsx(snap)
    fname = f"thematic-{snap.year}q{snap.quarter}"
    if snap.month:
        fname += f"-m{snap.month:02d}"
    fname += f"-{snap.work_type_id[:8]}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
