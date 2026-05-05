"""Resource Planning v2 endpoints — solver optimize + quality metric."""

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.plan_item_dependency import PlanItemDependency
from app.models.resource_plan import ResourcePlan
from app.models.resource_plan_assignment import ResourcePlanAssignment
from app.schemas.resource_planning_v2 import OptimizeResponse, QualityMetricSchema
from app.services.plan_quality_service import PlanQualityService
from app.services.pyjobshop_solver_service import PyJobShopSolverService

router = APIRouter()

# Допуск (в %) на ухудшение метрики перегрузок: если after.overload_days_pct
# вырос больше чем на эту величину относительно before, форк отклоняется.
OVERLOAD_TOLERANCE_PCT = 1.0


def _is_strictly_worse(before, after) -> bool:
    """True если after хуже before по перегрузкам или просрочкам.

    Перегрузки сравниваются с допуском (solver может слегка ухудшить
    утилизацию ради лучшей раскладки). Просрочки — без допуска: больше
    просрочек никогда не считаем приемлемым.
    """
    overload_worse = (
        after.overload_days_pct - before.overload_days_pct > OVERLOAD_TOLERANCE_PCT
    )
    late_worse = after.late_count > before.late_count
    return overload_worse or late_worse


@router.get("/{plan_id}/quality", response_model=QualityMetricSchema)
def get_plan_quality(plan_id: str, db: Session = Depends(get_db)) -> QualityMetricSchema:
    """Метрика качества плана: % перегрузок, просрочки, использование ёмкости."""
    try:
        metric = PlanQualityService(db).compute(plan_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return QualityMetricSchema(
        plan_id=metric["plan_id"],
        overload_days_pct=metric["overload_days_pct"],
        late_count=metric["late_count"],
        mean_utilization_pct=metric["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )


@router.post("/{plan_id}/optimize", response_model=OptimizeResponse)
def optimize_plan(plan_id: str, db: Session = Depends(get_db)) -> OptimizeResponse:
    """PyJobShop-оптимизация плана: создаёт форк с пересчитанными датами и исполнителями.

    Шаги:
    1. Вычисляет метрику качества «до».
    2. Запускает PyJobShopSolverService (до 30 с). При INFEASIBLE → 409.
    3. Клонирует план (форк) со всеми назначениями (включая is_pinned) и зависимостями.
    4. Применяет результат солвера к назначениям форка по phase-коду (не по индексу).
    5. Пинованные строки не перезаписываются (солвер их уже уважал; здесь — защитная проверка).
    6. Возвращает new_plan_id, before/after метрики, solver_status, solve_time_ms.
    """
    src = db.get(ResourcePlan, plan_id)
    if src is None:
        raise HTTPException(status_code=404, detail="ResourcePlan not found")

    # 1. Метрика «до»
    quality_svc = PlanQualityService(db)
    before_raw = quality_svc.compute(plan_id)
    before = QualityMetricSchema(
        plan_id=before_raw["plan_id"],
        overload_days_pct=before_raw["overload_days_pct"],
        late_count=before_raw["late_count"],
        mean_utilization_pct=before_raw["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )

    # 2. Запуск солвера
    result = PyJobShopSolverService(db).solve(plan_id)

    if result["solver_status"] == "INFEASIBLE":
        infeasible_sample = result["infeasible_items"][:5]
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Solver could not find a feasible schedule",
                "infeasible_items": infeasible_sample,
            },
        )

    # 3. Клонирование плана
    fork = ResourcePlan(
        scenario_id=src.scenario_id,
        team=src.team,
        quarter=src.quarter,
        year=src.year,
        status="ready",
        parent_plan_id=src.id,
        is_baseline=False,
        label="auto-PyJobShop",
    )
    db.add(fork)
    db.flush()  # fork.id теперь доступен

    # Клонируем назначения (включая is_pinned)
    src_assignments = list(
        db.scalars(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == src.id
            )
        )
    )
    fork_assignment_map: dict[str, ResourcePlanAssignment] = {}
    for a in src_assignments:
        fork_a = ResourcePlanAssignment(
            plan_id=fork.id,
            backlog_item_id=a.backlog_item_id,
            phase=a.phase,
            employee_id=a.employee_id,
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
            is_pinned=a.is_pinned,
        )
        db.add(fork_a)
        # Ключ: (backlog_item_id, phase) для последующего применения результата.
        # Если несколько строк с одинаковым (item, phase) — сохраняем первую;
        # solver также группирует по phase, поэтому соответствие однозначно.
        key = (a.backlog_item_id, a.phase)
        if key not in fork_assignment_map:
            fork_assignment_map[key] = fork_a

    # Клонируем зависимости
    src_deps = list(
        db.scalars(
            select(PlanItemDependency).where(PlanItemDependency.plan_id == src.id)
        )
    )
    for d in src_deps:
        db.add(
            PlanItemDependency(
                plan_id=fork.id,
                from_item_id=d.from_item_id,
                to_item_id=d.to_item_id,
                dep_type=d.dep_type,
                lag_days=d.lag_days,
                source=d.source,
            )
        )

    # 4. Применяем результат солвера к назначениям форка по phase-коду.
    # При авто-сплите один (item, phase) может дать N PhaseAllocation с chunk_index 0..N-1.
    # chunk_index=0 обновляет существующую строку; chunk_index>0 создаёт доп. строки.
    for solver_a in result["assignments"]:
        item_id = solver_a["backlog_item_id"]
        for phase_alloc in solver_a["phase_breakdown"]:
            phase = phase_alloc["phase"]
            chunk_idx = phase_alloc.get("chunk_index", 0)
            chunks_total = phase_alloc.get("chunks_total", 1)
            fork_row = fork_assignment_map.get((item_id, phase))
            if fork_row is None:
                continue
            # 5. Пинованные строки не перезаписываем
            if fork_row.is_pinned:
                continue
            if chunk_idx == 0:
                # Первый кусок — обновляем существующую строку
                fork_row.start_date = phase_alloc["start_date"]
                fork_row.end_date = phase_alloc["end_date"]
                fork_row.part_number = 1
                if phase_alloc["employee_id"] is not None:
                    fork_row.employee_id = phase_alloc["employee_id"]
            else:
                # Дополнительный кусок — новая строка в форке
                extra = ResourcePlanAssignment(
                    plan_id=fork.id,
                    backlog_item_id=item_id,
                    phase=phase,
                    employee_id=phase_alloc["employee_id"] or fork_row.employee_id,
                    part_number=chunk_idx + 1,
                    hours_allocated=phase_alloc["hours"],
                    start_date=phase_alloc["start_date"],
                    end_date=phase_alloc["end_date"],
                    is_on_critical_path=False,
                    slack_days=None,
                    is_pinned=False,
                )
                db.add(extra)

    db.commit()

    # 6. Метрика «после»
    after_raw = quality_svc.compute(fork.id)
    after = QualityMetricSchema(
        plan_id=after_raw["plan_id"],
        overload_days_pct=after_raw["overload_days_pct"],
        late_count=after_raw["late_count"],
        mean_utilization_pct=after_raw["mean_utilization_pct"],
        computed_at=datetime.now(timezone.utc),
    )

    # 7. Safety net: если форк хуже исходного — удалить и вернуть 409.
    # Без этого пользователь получает «оптимизированный» план с
    # перегрузками 23% вместо исходных 1.83%.
    if _is_strictly_worse(before, after):
        db.delete(fork)
        db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Solver ухудшил план — форк отклонён",
                "before": {
                    "overload_days_pct": before.overload_days_pct,
                    "late_count": before.late_count,
                },
                "after": {
                    "overload_days_pct": after.overload_days_pct,
                    "late_count": after.late_count,
                },
            },
        )

    return OptimizeResponse(
        new_plan_id=fork.id,
        before=before,
        after=after,
        solver_status=result["solver_status"],
        solve_time_ms=result["solve_time_ms"],
        infeasible_items=result["infeasible_items"],
    )


def _apply_solver_result_as_fork(
    db: Session, src: ResourcePlan, result: dict
) -> ResourcePlan:
    """Создаёт форк плана и применяет результат солвера к его назначениям.

    Вынесено из ``optimize_plan`` для переиспользования в SSE-стриме.
    """
    fork = ResourcePlan(
        scenario_id=src.scenario_id,
        team=src.team,
        quarter=src.quarter,
        year=src.year,
        status="ready",
        parent_plan_id=src.id,
        is_baseline=False,
        label="auto-PyJobShop",
    )
    db.add(fork)
    db.flush()

    src_assignments = list(
        db.scalars(
            select(ResourcePlanAssignment).where(
                ResourcePlanAssignment.plan_id == src.id
            )
        )
    )
    fork_assignment_map: dict[tuple, ResourcePlanAssignment] = {}
    for a in src_assignments:
        fork_a = ResourcePlanAssignment(
            plan_id=fork.id,
            backlog_item_id=a.backlog_item_id,
            phase=a.phase,
            employee_id=a.employee_id,
            part_number=a.part_number,
            hours_allocated=a.hours_allocated,
            start_date=a.start_date,
            end_date=a.end_date,
            is_on_critical_path=a.is_on_critical_path,
            slack_days=a.slack_days,
            is_pinned=a.is_pinned,
        )
        db.add(fork_a)
        key = (a.backlog_item_id, a.phase)
        if key not in fork_assignment_map:
            fork_assignment_map[key] = fork_a

    src_deps = list(
        db.scalars(
            select(PlanItemDependency).where(PlanItemDependency.plan_id == src.id)
        )
    )
    for d in src_deps:
        db.add(
            PlanItemDependency(
                plan_id=fork.id,
                from_item_id=d.from_item_id,
                to_item_id=d.to_item_id,
                dep_type=d.dep_type,
                lag_days=d.lag_days,
                source=d.source,
            )
        )

    for solver_a in result["assignments"]:
        item_id = solver_a["backlog_item_id"]
        for phase_alloc in solver_a["phase_breakdown"]:
            phase = phase_alloc["phase"]
            chunk_idx = phase_alloc.get("chunk_index", 0)
            fork_row = fork_assignment_map.get((item_id, phase))
            if fork_row is None or fork_row.is_pinned:
                continue
            if chunk_idx == 0:
                fork_row.start_date = phase_alloc["start_date"]
                fork_row.end_date = phase_alloc["end_date"]
                fork_row.part_number = 1
                if phase_alloc["employee_id"] is not None:
                    fork_row.employee_id = phase_alloc["employee_id"]
            else:
                extra = ResourcePlanAssignment(
                    plan_id=fork.id,
                    backlog_item_id=item_id,
                    phase=phase,
                    employee_id=phase_alloc["employee_id"] or fork_row.employee_id,
                    part_number=chunk_idx + 1,
                    hours_allocated=phase_alloc.get("hours", 0.0),
                    start_date=phase_alloc["start_date"],
                    end_date=phase_alloc["end_date"],
                    is_on_critical_path=False,
                    slack_days=None,
                    is_pinned=False,
                )
                db.add(extra)

    db.commit()
    return fork


@router.post("/{plan_id}/optimize/stream")
async def optimize_plan_stream(
    plan_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
):
    """SSE-стрим прогресса оптимизации.

    Solver блокирующий (CP-SAT), поэтому крутится в потоке через
    ``asyncio.to_thread``. Параллельно отдаём heartbeat-события каждые 1 сек,
    чтобы фронт показывал прогресс. По завершении — событие ``done`` с
    new_plan_id и метриками before/after.

    События:
    - ``progress`` — heartbeat с elapsed_ms
    - ``done`` — финальный результат
    - ``error`` — INFEASIBLE или ошибка solver'а
    - ``cancelled`` — клиент отвалился
    """
    src = db.get(ResourcePlan, plan_id)
    if src is None:
        raise HTTPException(status_code=404, detail="ResourcePlan not found")

    quality_svc = PlanQualityService(db)
    before_raw = quality_svc.compute(plan_id)
    before_payload = {
        "plan_id": before_raw["plan_id"],
        "overload_days_pct": before_raw["overload_days_pct"],
        "late_count": before_raw["late_count"],
        "mean_utilization_pct": before_raw["mean_utilization_pct"],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    async def event_gen():
        t0 = time.monotonic()
        solve_done = asyncio.Event()
        result_holder: dict = {}

        def run_solver():
            try:
                result_holder["result"] = PyJobShopSolverService(db).solve(plan_id)
            except Exception as e:  # noqa: BLE001
                result_holder["error"] = str(e)
            finally:
                solve_done.set()

        solver_task = asyncio.create_task(asyncio.to_thread(run_solver))

        try:
            # Heartbeat пока solver крутится
            while not solve_done.is_set():
                if await http_request.is_disconnected():
                    solver_task.cancel()
                    yield f"data: {json.dumps({'type': 'cancelled'})}\n\n".encode()
                    return
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                yield (
                    f"data: {json.dumps({'type': 'progress', 'elapsed_ms': elapsed_ms})}\n\n"
                ).encode()
                try:
                    await asyncio.wait_for(solve_done.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

            await solver_task

            if "error" in result_holder:
                yield f"data: {json.dumps({'type': 'error', 'detail': result_holder['error']})}\n\n".encode()
                return

            result = result_holder["result"]

            if result["solver_status"] == "INFEASIBLE":
                yield (
                    f"data: {json.dumps({'type': 'error', 'detail': 'Solver could not find feasible schedule', 'infeasible_items': result['infeasible_items'][:5]})}\n\n"
                ).encode()
                return

            # Применяем форк
            fork = _apply_solver_result_as_fork(db, src, result)
            after_raw = quality_svc.compute(fork.id)
            after_payload = {
                "plan_id": after_raw["plan_id"],
                "overload_days_pct": after_raw["overload_days_pct"],
                "late_count": after_raw["late_count"],
                "mean_utilization_pct": after_raw["mean_utilization_pct"],
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }

            # Safety net: если форк хуже — удалить, отдать error.
            class _M:
                def __init__(self, d):
                    self.overload_days_pct = d["overload_days_pct"]
                    self.late_count = d["late_count"]

            if _is_strictly_worse(_M(before_payload), _M(after_payload)):
                db.delete(fork)
                db.commit()
                yield (
                    f"data: {json.dumps({'type': 'error', 'detail': 'Solver ухудшил план — форк отклонён', 'before': before_payload, 'after': after_payload}, ensure_ascii=False)}\n\n"
                ).encode()
                return

            done_event = {
                "type": "done",
                "new_plan_id": fork.id,
                "before": before_payload,
                "after": after_payload,
                "solver_status": result["solver_status"],
                "solve_time_ms": result["solve_time_ms"],
                "infeasible_items": result["infeasible_items"],
            }
            yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n".encode()
        finally:
            if not solver_task.done():
                solver_task.cancel()

    return StreamingResponse(event_gen(), media_type="text/event-stream")
