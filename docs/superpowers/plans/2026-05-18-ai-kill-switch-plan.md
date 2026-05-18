# AI Kill Switch — Implementation Plan

Spec: [2026-05-18-ai-kill-switch-design.md](../specs/2026-05-18-ai-kill-switch-design.md)

## Phase 1 — Backend foundation

1. `app/services/llm/base.py`: добавить `is_ai_enabled(db) -> bool` рядом с `get_llm_provider`. Default False (нет ключа → False).
2. `app/core/ai_deps.py` (новый): `require_ai_enabled(db: Session = Depends(get_db))` raise 503 при OFF.
3. `app/api/endpoints/ai_status.py` (новый): `GET /ai-status` → `{enabled: bool}`. Регистрируем в `app/api/router.py` с `_auth_dep` (не admin).
4. `app/api/endpoints/settings.py`: добавить `ai_enabled` в `_is_allowed_generic_key`.

## Phase 2 — Backend gating

5. `app/api/endpoints/llm.py`: `Depends(require_ai_enabled)` на `/test`, `/regenerate-all`, `/gemini/models`, `/openrouter/models`.
6. `app/api/endpoints/projects.py`: `Depends(require_ai_enabled)` на `regenerate_summary`.
7. `app/api/endpoints/work_type_report.py`: `Depends(require_ai_enabled)` на build, build/stream, candidates/accept, candidates/merge, candidates/ignore, manual-classify, themes/aliases POST+DELETE.
8. `app/api/endpoints/executive.py`: `Depends(require_ai_enabled)` на `dashboard/build`.
9. `app/jobs/regenerate_summaries.py`: early-return при OFF.

## Phase 3 — Backend tests

10. `tests/api/test_ai_kill_switch.py`: 9 тестов (см. спеку).

## Phase 4 — Frontend foundation

11. `frontend/src/hooks/useAiEnabled.ts`: TanStack Query hook, staleTime 60s.
12. `frontend/src/components/shared/AiGate.tsx`: cloneElement + Tooltip.
13. `frontend/src/components/shared/AiOffNotice.tsx`: full-page стаб.
14. `frontend/src/api/aiStatus.ts`: `getAiStatus()` + `setAiEnabled(bool)`.

## Phase 5 — Frontend wiring

15. `frontend/src/components/settings/AITab.tsx`: Switch сверху, Form disabled при OFF, alert.
16. `frontend/src/pages/ProjectsPage.tsx` + `ProjectListCard`/`ProjectDetailPanel`/`ProjectAnalysisView`/`ProjectPresentationView`: refresh buttons → `<AiGate>`.
17. `frontend/src/components/executive/AISummary.tsx`: при OFF — show stale + плашка; build button → `<AiGate>`.
18. `frontend/src/pages/WorkTypeReportPage.tsx`: early-return `<AiOffNotice>` при OFF.

## Phase 6 — Verify + push

19. `py -3.10 -m pytest tests/api/test_ai_kill_switch.py -v`
20. `cd frontend && npm run lint && npm run build`
21. Commit + push.
