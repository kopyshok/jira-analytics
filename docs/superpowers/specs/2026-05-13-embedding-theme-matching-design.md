# Embedding-based theme matching for thematic reports

**Date:** 2026-05-13
**Status:** Approved (brainstorming complete)
**Scope:** Backend (Python) + Frontend (TypeScript) + Alembic migration

## Problem

Текущая Map-фаза тематического отчёта ([app/services/llm/work_type_classifier.py](../../../app/services/llm/work_type_classifier.py)) полагается на LLM-классификатор: задача + словарь тем → `theme_id` или `candidate_name`. LLM матчит «на глаз» по семантике текста темы. Слабости:

- При узких семантических различиях (Себестоимость vs Таможенная стоимость, Обмен vs Интеграция) LLM создаёт нового кандидата вместо матча в существующую тему.
- `/candidates/merge` перепривязывает существующие задачи, но **не обучает** систему: новые похожие задачи снова станут кандидатами.
- Словарь не растёт от практики — пользователь сливает одну и ту же связку темы каждый квартал.

## Цель

Добавить детерминированный embedding-based матчинг как первичный фильтр перед LLM. Каждое слияние кандидата автоматически расширяет «зону притяжения» темы в векторном пространстве — система обучается без переписывания LLM-промптов.

## Решения

1. **Embedding-first, LLM fallback** — embedding ищет ближайшую тему по cosine. Если ≥ threshold → match без LLM. Если ниже → текущий LLM-классификатор отрабатывает как сейчас.
2. **Centroid темы** — вектор темы = weighted mean (text-vector × 1.0 + each top-K issue-vector × 0.5), top-K по часам, K=20.
3. **Full CRUD алиасов** — пользователь может добавлять/удалять алиасы вручную через UI темы; merge кандидата автоматически добавляет `proposed_name` в алиасы.
4. **Lazy backfill** — миграция создаёт пустые колонки; первый ребилд отчёта после деплоя считает векторы на лету. Никаких блокирующих startup-задач.

## Архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│ Map-фаза по задаче:                                              │
│                                                                  │
│  1. embed_issue(issue) → vec_i                                   │
│     ├─ если IssueClassification.input_embedding кэширован и     │
│     │  input_hash совпадает + embedding_model_version совпадает │
│     │  → reuse                                                   │
│     └─ иначе → EmbeddingService.encode(issue text) → store       │
│                                                                  │
│  2. for each Theme: similarity(vec_i, theme.embedding_vec)       │
│     ├─ theme.embedding_vec лениво вычисляется при первом доступе│
│     └─ centroid: weighted_mean(text_vec, top_issues_vec)         │
│                                                                  │
│  3. best_theme, best_score = argmax(similarities)                │
│     ├─ if best_score ≥ THRESHOLD → theme_id = best_theme.id      │
│     │   match_method = "embedding"                               │
│     └─ else → LLM classifier (existing logic)                    │
│         match_method = "llm"                                     │
│                                                                  │
│  4. persist IssueClassification с input_embedding +              │
│     embedding_model_version + match_method                       │
└─────────────────────────────────────────────────────────────────┘
```

## Компоненты

### EmbeddingService (`app/services/llm/embedding_service.py`)

Singleton-обёртка над sentence-transformers.

- **Модель:** `intfloat/multilingual-e5-base` (278 MB, 768-dim, multilingual, top для русского на MTEB-ru).
- **Pin:** model name + git SHA revision хардкодятся как константы в коде. При смене модели вручную обновляются обе.
- **Загрузка:** через FastAPI lifespan event на startup, один раз в глобальный singleton. Cold load 5-10 с.
- **Методы:**
  - `encode_text(text: str) → np.ndarray[768]` — для одного текста.
  - `encode_batch(texts: list[str]) → np.ndarray[N, 768]` — для bulk-операций (используется в backfill центроидов).
  - `MODEL_NAME`, `MODEL_REVISION`, `EMBEDDING_DIM`, `MODEL_VERSION` — публичные константы. `MODEL_VERSION` = строка вида `"e5-base-{revision_short}"` для записи в БД и определения протухших векторов.
- **Формат для модели:** e5-семейство требует префиксы `"query: "` и `"passage: "` в инпуте. Сервис подставляет автоматически (issue/theme = passage; новая задача на матчинге = query).
- **Нормализация:** возвращает L2-normalized векторы (cosine = dot product).

### Embedding storage

- `Theme.embedding` — `LargeBinary` (BLOB), 768 × 4 = 3072 байта. Pickled numpy array.
- `Theme.embedding_model_version` — `String(64)`. Несовпадение с `EmbeddingService.MODEL_VERSION` → вектор протух, пересчитать.
- `Theme.aliases` — `JSON` колонка (или `Text` с JSON-сериализацией). `list[str]`. Дедуп по нормализованному ключу (lower-case, strip).
- `Theme.embedding_updated_at` — `DateTime`. Для дебага.
- `IssueClassification.input_embedding` — `LargeBinary`.
- `IssueClassification.embedding_model_version` — `String(64)`.
- `IssueClassification.match_method` — `String(16)` ∈ {`embedding`, `llm`, `null`}. Аналитика «сколько задач сматчилось без LLM».
- `IssueClassification.match_score` — `Float`. Cosine при `match_method = embedding`. Null иначе.

### ThemeEmbeddingService (`app/services/llm/theme_embedding_service.py`)

Считает centroid темы.

- `compute_theme_embedding(theme: Theme, top_issues: list[Issue]) → np.ndarray`:
  - `text` = `f"{theme.name}. {theme.description or ''}. Также покрывает: {', '.join(theme.aliases)}"`
  - `text_vec` = `EmbeddingService.encode_text(text)`
  - `issue_vecs` = batch-encode summaries top-K issues (top-K по часам за всё время; K = `THEME_CENTROID_TOP_K` = 20)
  - `centroid` = `normalize(text_vec * 1.0 + sum(issue_vecs * 0.5))` (взвешенная сумма, потом L2-norm)
  - Если у темы 0 привязанных задач → centroid = text_vec only.
- `recompute_theme_embedding(theme_id: str, db: Session)` — top-level entry: load theme, load top-K issues, compute, persist. Bump `embedding_updated_at`. Вызывается:
  - На lazy-доступе (первое обращение в Map-фазе).
  - На редактировании темы (изменение name/description/aliases).
  - На merge/accept кандидата.
  - На admin-кнопке «Пересчитать embedding темы».

### EmbeddingMatcher (`app/services/llm/embedding_matcher.py`)

Поиск лучшей темы для задачи.

- `find_best_theme(issue_vec, themes: list[Theme], threshold: float) → (Theme | None, float)`:
  - Загрузить `theme.embedding` для каждой темы (лениво, через `ThemeEmbeddingService.recompute_theme_embedding` если пустой/протухший).
  - Cosine similarity = `np.dot(issue_vec, theme_vec)` (оба нормированы).
  - Вернуть пару `(best_theme, best_score)` если `best_score ≥ threshold`, иначе `(None, best_score)`.
- Threshold по умолчанию: **0.78**. Хранится в `AppSetting` под ключом `theme_match_embedding_threshold`. Читается через `_get_setting`.

### Изменения в Map-фазе (`work_type_classifier.py` + оркестратор)

Сейчас оркестратор внутри `work_type_report_service.build` вызывает `WorkTypeClassifier.prepare` → LLM. Изменения:

1. **Перед** вызовом LLM считаем `issue_vec` через `EmbeddingService`. Кэш-чек по `input_hash + embedding_model_version`.
2. Вызываем `EmbeddingMatcher.find_best_theme(issue_vec, active_themes, threshold)`.
3. Если есть match → собираем `ClassificationResult(theme_id=best.id, candidate_name=None, confidence=score, ...)` **минуя LLM**. `match_method='embedding'`, `match_score=score`.
4. Если match нет → LLM-классификатор как сейчас. `match_method='llm'`, `match_score=None`.
5. `IssueClassification.input_embedding` сохраняется в обоих случаях.

`markers` / `area` / `nature` / `contribution_text` при embedding-матче остаются None. Это новое поведение: они нужны только Cluster-фазе для кандидатов. Если задача сматчилась через embedding — кластеризация не нужна. UI должен корректно обрабатывать `markers=[]` (уже умеет).

### Aliases CRUD

**Backend endpoints** (новые в `app/api/endpoints/work_type_report.py` либо в новом `theme_aliases.py`):

- `POST /work-type-report/themes/{theme_id}/aliases` — body `{alias: str}`. Дедуп. 409 на дубль. Bump `theme_dict_version`. Recompute embedding темы.
- `DELETE /work-type-report/themes/{theme_id}/aliases?alias=<text>` — удалить по точному значению. Bump `theme_dict_version`. Recompute embedding.

**Изменения в merge endpoint** (`POST /candidates/merge`):

Сейчас просто перепривязывает классификации. Добавить:
- Записать `payload.proposed_name` в `Theme.aliases` (если ещё нет).
- Bump `theme_dict_version`.
- Recompute embedding темы.

**Frontend** (`frontend/src/pages/WorkTypeReportPage.tsx` или редактор темы):

- В форме редактирования темы — chip-list алиасов (AntD `Tag` с `closable`).
- Input «добавить алиас» + кнопка/Enter.
- Каждый chip с крестиком удаляет alias.
- Алиасы отображаются также в read-only режиме (просмотр темы).

### Threshold админ-настройка

- Поле `theme_match_embedding_threshold` в `AppSetting`, дефолт `"0.78"`.
- Endpoint `PUT /work-type-report/settings/threshold` (или через generic `/settings/generic`).
- UI: одно поле в админке «Тематический отчёт» / либо на странице «Словарь тем» — слайдер 0.5–0.95 шагом 0.01 с подсказкой «выше = строже».

## Жизненный цикл embeddings

| Событие | Что происходит |
|---|---|
| Создание темы | `Theme.embedding = None`. Считается при первом доступе в Map-фазе или при admin-кнопке. |
| Правка имени/описания темы | На save → bump `dict_version` + recompute embedding темы. |
| Добавление/удаление алиаса | bump `dict_version` + recompute embedding темы. |
| Merge кандидата | проставляется theme_id у существующих классификаций + alias добавляется в тему + bump `dict_version` + recompute embedding. |
| Accept кандидата | создаётся новая тема + перепривязка классификаций + recompute embedding новой темы. |
| Архивация темы | Тема исключается из матчинга. Embedding не пересчитывается. |
| Создание/изменение задачи | На следующем ребилде отчёта: `input_hash` ≠ кэш → перезапишется embedding и классификация. |
| Смена `EmbeddingService.MODEL_VERSION` | Все векторы протухают (определяется сравнением `embedding_model_version`). На ребилде идёт массовый recompute. |

## Производительность

- Cold load модели: 5-10 с на старте backend (один раз).
- Encode одного текста: ~30-50 мс на CPU 2 vCPU.
- Encode batch 32: ~200-300 мс (throughput выше).
- Cosine similarity 1 задача × 20 тем: < 1 мс (numpy dot).
- Полный ребилд отчёта на 5-15k задач: первый раз +10-20 мин (embeddings), потом инкрементально (только новые/изменённые задачи).

## VPS-готовность

Фиксируется уже на этапе локальной разработки:

- **CPU-only torch wheel**: `requirements.txt` получает блок:
  ```
  --extra-index-url https://download.pytorch.org/whl/cpu
  torch==2.3.1+cpu
  sentence-transformers==2.7.0
  numpy>=1.26
  ```
  Без `+cpu` суффикса pip тащит ~2 GB CUDA-runtime, который не нужен.
- **HF cache** в env: `HF_HOME` читается из переменной окружения, дефолт `~/.cache/huggingface`. Документируется в README. Прод-конфиг — `HF_HOME=/var/cache/huggingface`.
- **Pre-baking опция**: README раздел «Деплой на VPS» с тремя сценариями (с outbound, без outbound, docker).
- **Lifespan singleton**: модель грузится в `app.main:lifespan`, выгружается при shutdown.

## Тесты

| Что | Где |
|---|---|
| `EmbeddingService.encode_text` возвращает float32 normalized 768-dim | `tests/services/test_embedding_service.py` |
| `EmbeddingService.encode_batch` batch ≥ 2 текстов | то же |
| L2-norm векторов | то же |
| `ThemeEmbeddingService.compute_theme_embedding` без задач = text_vec only | `tests/services/test_theme_embedding_service.py` |
| Same с K=3 задачами = weighted mean | то же |
| `EmbeddingMatcher.find_best_theme` возвращает best > threshold | `tests/services/test_embedding_matcher.py` |
| `find_best_theme` возвращает None если все < threshold | то же |
| Map-фаза: embedding-first путь обходит LLM | `tests/services/test_work_type_report_service.py` (mock provider, real EmbeddingService) |
| Map-фаза: LLM fallback срабатывает при низком score | то же |
| Cache hit по `input_hash + embedding_model_version` пропускает encode | то же |
| `Theme.aliases` add/delete endpoint работает | `tests/api/test_work_type_report.py` |
| Merge кандидата добавляет alias + recompute embedding | то же |
| Threshold setting GET/PUT | то же |
| Frontend: alias chip add/remove | (manual smoke, без e2e) |

## Out of scope

- Embedding других сущностей (worklog comments, project descriptions) — отдельная итерация.
- Адаптивный/обучаемый threshold per-theme — глобальный фиксированный достаточно для MVP.
- Hybrid retrieval (BM25 + embeddings) — overkill для текущего объёма.
- GPU-инференс — VPS без GPU.
- Многомодельный fallback (если e5-base падает — переключение на другую модель). При недоступности — текущий LLM-классификатор и так покрывает.

## Открытые риски

- **Качество e5-base на узких русских доменах** (1С-сленг, бухгалтерская лексика). Если cosine ≥ 0.78 даст много false positives — поднимем threshold до 0.82-0.85. Откалибруется на первых 100 реальных задачах.
- **Размер docker-образа +500 MB** (torch CPU + transformers). Приемлемо.
- **Cold-load 5-10 с** при холодном старте — пользователь, перезагрузивший backend, увидит небольшую задержку на первом запросе.
