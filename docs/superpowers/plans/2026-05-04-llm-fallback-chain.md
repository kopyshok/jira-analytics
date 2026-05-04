# LLM fallback chain — устойчивость к upstream rate-limit

**Дата:** 2026-05-04
**Статус:** запланировано
**Приоритет:** средний (workaround есть — сменить модель вручную)
**Оценка:** ~30 минут

## Контекст

После запуска OpenRouter (commit `29028f0` + `7357103`) выяснилось:
популярные free-модели (например `qwen/qwen3-next-80b-a3b-instruct:free`)
часто отдают HTTP 429 от upstream-провайдера (Venice/etc), даже когда
ключ валиден и общая квота OpenRouter не исчерпана. Один регенерат
саммари → 503 → пользователь идёт в /settings, выбирает другую модель,
повторяет. Раздражает.

Healthcheck уже не страдает (использует `/auth/key`), но реальная
генерация саммари (`POST /projects/{key}/regenerate-summary`) падает
на первом 429.

## Цель

Авто-фоллбэк: при 429/5xx на основной модели — пробовать список
запасных по порядку. Возвращать ошибку только если все модели
упали.

## Реализация

### Backend

1. **AppSetting:** новый ключ `llm_openrouter_fallback_models` —
   CSV-строка `model_a,model_b,model_c`. Whitelist в `LLM_KEYS`.
2. **`OpenRouterProvider.__init__`** — принимает `fallback_models: list[str]`.
   Factory читает из AppSetting и передаёт.
3. **`summarize_project`** — обёртка вокруг `_call_model(model, ...)`:
   - try primary → success → return
   - except `httpx.HTTPStatusError` (status in {429, 502, 503, 504}):
     log warning + try next fallback
   - все упали → бросить последнюю ошибку
4. **`healthcheck`** не трогать — `/auth/key` достаточно.
5. **Meta поле:** в `meta['model']` писать **реально использованную**
   модель (не primary), чтобы UI показал какой fallback сработал.
6. **Логирование:** `logger.info("OpenRouter fallback %s → %s after 429", primary, fallback)`.

### Frontend (`AITab.tsx`)

1. **Новое поле формы:** `openrouter_fallback_models` — `Select` с
   `mode="multiple"`, options из того же списка free-моделей.
   Default: `[gemma-3-27b-it:free, glm-4.5-air:free, gpt-oss-120b:free]`
   (нагрузка на разные провайдеры).
2. **Hint:** «При 429 на основной модели запросы пробуются по этому
   списку по порядку. Используйте модели от РАЗНЫХ провайдеров для
   максимальной устойчивости.»
3. **`onSave`:** PUT `llm_openrouter_fallback_models` с CSV-значением.

### Тесты

1. `respx`-mock: primary → 429, fallback[0] → 200. Проверить, что
   результат пришёл из fallback[0], `meta['model']` совпадает.
2. Все упали → exception проброшен.
3. Empty fallback list → старое поведение (одна попытка).

### Миграция

Не нужна — AppSetting добавляется через generic CRUD.

## Альтернативы (отвергнуто)

- **Retry той же модели через N секунд** — upstream rate-limit держится
  минутами, retry не помогает.
- **Auto-pick модели по live-списку** — слишком магия, юзер теряет
  контроль.
- **Только UI-предупреждение «модель часто 429, выбери другую»** —
  не решает проблему, только перекладывает на юзера.

## Связанные

- Memory: `project_openrouter_provider_shipped`
- Commits: `29028f0` (provider), `8e292ec` (error surface), `7357103` (healthcheck fix)
