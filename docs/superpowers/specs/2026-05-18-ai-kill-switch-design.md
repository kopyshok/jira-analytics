# AI Kill Switch — Design

**Дата:** 2026-05-18

## Контекст

Сервис разворачивается на корпоративном сервере. Внешние LLM-провайдеры (Google Gemini, OpenRouter) временно недоступны/нежелательны. Нужен глобальный «рубильник» в настройках, который:

1. Блокирует все исходящие LLM-вызовы на бэке.
2. Деактивирует все AI-кнопки на фронте с подсказкой «выключено администратором».
3. Полностью AI-страницы (Тематический отчёт) при выключенном ИИ показывают заглушку — скрипты не работают.
4. Существующие AI-саммари в БД остаются видимыми (не скрываем кэшированные данные).
5. По умолчанию на свежем сервере **выключен**.

## Архитектура

### Бэкенд

**Хранение состояния.** Используем существующий `AppSetting` (flat KV), новый ключ:

- `ai_enabled` (`"true"` / `"false"`, default `"false"` если ключа нет).

Чтения через хелпер `is_ai_enabled(db: Session) -> bool` в `app/services/llm/base.py` рядом с `get_llm_provider`. Без миграции — `AppSetting` уже есть.

**Dependency.** В `app/services/llm/base.py` (или новый `app/core/ai_deps.py`):

```python
def require_ai_enabled(db: Session = Depends(get_db)) -> None:
    if not is_ai_enabled(db):
        raise HTTPException(status_code=503, detail="AI disabled by administrator")
```

**Применение.** Точечно на эндпоинтах (не на роутерах целиком — некоторые роутеры включают чтение кэшей, которое мы оставляем доступным):

- `POST /llm/test`, `POST /llm/regenerate-all`, `GET /llm/gemini/models`, `GET /llm/openrouter/models` — все мутирующие/живые операции.
- `GET /llm/prompt-default` — оставляем доступным (статика).
- `POST /projects/{key}/regenerate-summary` — блок.
- `GET /projects/{key}/summary` — оставляем доступным (читает кэш).
- `POST /work-type-report` (build), `POST /work-type-report/build/stream`, `POST /work-type-report/candidates/accept`, `POST /work-type-report/candidates/merge`, `POST /work-type-report/candidates/ignore`, `POST /work-type-report/manual-classify`, `POST /work-type-report/themes/{id}/aliases`, `DELETE /work-type-report/themes/{id}/aliases` — все мутирующие. `GET /work-type-report` (read snapshot) оставляем — старые отчёты видны.
- `POST /executive/dashboard/build` — блок. `GET /executive/dashboard` — оставляем (кэш).

**Cron.** В `app/jobs/regenerate_summaries.py` функция `regenerate_outdated_summaries` — ранний return при `ai_enabled=false` с логом `info`.

**Публичный статус-эндпоинт.** `GET /settings/ai-status` → `{enabled: bool}`. Доступен любому авторизованному пользователю (не admin), потому что фронт читает его на каждой странице. Делаем под `_auth_dep`, а не `_admin_dep`. Внутри router `settings.py` — но регистрируем отдельно через прокси или выносим в `auth_endpoints` / `users_endpoints`. Решение: создать новый мини-роутер `app/api/endpoints/ai_status.py` с одним GET, регистрировать под `_auth_dep`.

### Фронтенд

**Хук `useAiEnabled`** (`frontend/src/hooks/useAiEnabled.ts`):

- TanStack Query: `useQuery({ queryKey: ['ai-status'], queryFn: () => api.get('/ai-status'), staleTime: 60_000 })`.
- Возвращает `{ enabled: boolean, isLoading: boolean }`. На время загрузки считаем `enabled=true` (оптимистично — иначе кнопки мигают).

**Компонент `<AiGate>`** (`frontend/src/components/shared/AiGate.tsx`):

```tsx
<AiGate>
  <Button>Перегенерировать саммари</Button>
</AiGate>
```

При `enabled=false`: клонирует child с `disabled`, оборачивает в `Tooltip "ИИ выключен администратором"`. Поддерживает props children (один React-element).

Для немутирующего «отображения данных» — отдельный компонент `<AiOffNotice>` (плашка с иконкой и текстом «ИИ выключен администратором»).

**Точки внедрения:**

| Место | Поведение |
|---|---|
| `Settings → AI` | Сверху Switch «ИИ включён» (admin-only setting через `PUT /settings/generic` с ключом `ai_enabled`). Если OFF — Form disabled + плашка сверху «ИИ выключен. Включите чтобы редактировать настройки». Кнопки «Сохранить»/«Проверить подключение»/«Перегенерировать все саммари» — disabled. |
| `/projects` (ProjectListCard / ProjectDetailPanel / ProjectAnalysisView / ProjectPresentationView) | Кнопка «Обновить саммари» обёрнута в `<AiGate>`. Сами карточки с уже сгенерированными данными — отображаются как есть. |
| `/executive` AISummary | Если OFF и `ai_summary` в snapshot есть — показываем как есть + маленькая плашка «ИИ выключен — данные могут быть устаревшими». Если OFF и кнопка «Обновить» — disabled через `<AiGate>`. |
| `/analytics/work-type-report` | На входе если OFF → ранний return из page-компонента, рендерим `<AiOffNotice>` на весь экран. Дочерние компоненты (Map/Cluster/Build) не монтируются, запросов в `useWorkTypeReport` не делается. |

**Изменение AI-настроек.** Switch вызывает `api.put('/settings/generic', { key: 'ai_enabled', value: 'true'/'false' })` → после успеха `queryClient.invalidateQueries({ queryKey: ['ai-status'] })`. Ключ `ai_enabled` нужно добавить в whitelist `_is_allowed_generic_key` в `app/api/endpoints/settings.py`.

### Тесты

**Backend (`tests/api/test_ai_kill_switch.py`):**

- `is_ai_enabled` default False, after set True returns True.
- `GET /ai-status` возвращает `{enabled: bool}`.
- `POST /llm/test` → 503 когда OFF.
- `POST /projects/{key}/regenerate-summary` → 503 когда OFF.
- `POST /work-type-report` (build) → 503 когда OFF.
- `POST /executive/dashboard/build` → 503 когда OFF.
- `GET /projects/{key}/summary` остаётся 200 (читает кэш).
- `GET /work-type-report` остаётся 200.
- Cron job `regenerate_outdated_summaries` — early return при OFF, не вызывает provider (мок).

**Frontend:** smoke не запускаем (memory `feedback_subagent_flow.md` допускает). Добавим один unit-тест на `AiGate` (если время есть) — children становится disabled при `enabled=false`.

## Обратная совместимость

- Свежий деплой: ключа `ai_enabled` нет → default OFF, всё блокируется.
- Существующий dev (моя локальная БД): после применения нужно один раз вручную включить через UI (или через `PUT /settings/generic`).
- Кэшированные саммари сохраняются как есть — read-эндпоинты не трогаем.

## Out of scope

- Per-user permission на ИИ. Только глобально.
- Audit log переключений (можно добавить позже).
- Удаление существующих саммари при выключении (B-вариант из брейнсторма, отвергнут).
