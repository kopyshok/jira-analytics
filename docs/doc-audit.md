# Аудит документации и мёртвого кода

Как защититься от случая «Claude гадает где кнопка, потому что доки врут».

## Правило источника правды

Когда правда в коде расходится с описанием в `CLAUDE.md` / `AGENTS.md` — **доки врут**, фиксим их. Не пытаемся подстроить код под доки.

Источники правды для текущего состояния:

| Что | Где правда |
|---|---|
| Маршруты `/foo` | `frontend/src/routes.tsx` |
| Lazy-страницы | `frontend/src/pages/lazyPages.tsx` |
| Вкладки `SettingsPage` | `frontend/src/pages/SettingsPage.tsx` (`items={[...]}`) |
| Вкладки `SyncHubPage` | `frontend/src/pages/SyncHubPage.tsx` |
| API роутеры | `app/api/router.py` (include + prefix) |
| Эндпоинты | `app/api/endpoints/*.py` (декораторы `@router.<method>`) |
| Таблицы БД | `app/models/__init__.py` |
| Миграции | `alembic/versions/` |
| AppSetting ключи | `app/api/endpoints/settings.py` |

Если CLAUDE.md ссылается на файл/функцию, которой нет — он устарел.

## Регулярный аудит (раз в 2 недели или после крупного рефакторинга)

### 1. Мёртвый frontend-код

```bash
cd frontend
# Установить knip один раз: npm i -D knip
npx knip
```

Отчёт покажет:
- Файлы без импортов (orphan).
- Экспорты, которые никто не использует.
- npm-зависимости, которые не подключены.

Альтернативы: `madge --orphans src/`, `ts-prune` (устарел).

### 2. Мёртвые маршруты

```bash
# Имена всех страниц, упомянутых в routes.tsx
grep -oE "[A-Z][a-zA-Z]+Page" frontend/src/routes.tsx | sort -u

# Сверить с реальными файлами в pages/
ls frontend/src/pages/*.tsx
```

Если файл в `pages/` не упомянут в `routes.tsx` И не импортируется как компонент — кандидат на удаление.

### 3. Мёртвый backend-код

```bash
# Установить vulture один раз: pip install vulture
vulture app/ --min-confidence 80
```

Также:
- Эндпоинты, не вызываемые с фронта: `rg "/api/v1/<prefix>/<path>" frontend/src` — если 0 совпадений, скорее всего мёртвый.
- Сервисные функции без вызовов: `rg "func_name\(" app/` — если только определение, проверь.

### 4. Drift в CLAUDE.md / AGENTS.md

Для каждой markdown-ссылки на файл в доках — проверить что файл существует:

```bash
# Найти все упоминания файлов вида path/file.py или (path/file.tsx)
grep -rE "\(([a-z][a-zA-Z_/-]+\.(py|tsx|ts|md))\)" CLAUDE.md AGENTS.md app/ frontend/ docs/ | \
  awk -F'[(:)]' '{print $NF}' | sort -u | \
  while read f; do [ -f "$f" ] || echo "MISSING: $f"; done
```

Любое `MISSING:` — устаревшая ссылка, чинить или удалять.

### 5. Drift таблицы routes ↔ AGENTS.md

После каждого добавления/удаления страницы — обязательно пройтись по таблице роутов в `frontend/CLAUDE.md` и обновить.

Проверка:
```bash
# Все пути из routes.tsx
grep -oE "path: '[^']+'" frontend/src/routes.tsx | sort -u
# Все пути упомянутые в CLAUDE.md
grep -oE "\`/[a-z][a-z-]*\`" frontend/CLAUDE.md AGENTS.md | sort -u
```

Различия — drift.

### 6. Миграции vs модели

```bash
alembic check  # есть ли «autogenerate diff» к текущим моделям
```

Если diff не пустой — миграции отстают от моделей.

### 7. Тесты, которые ничего не проверяют

```bash
py -3.10 -m pytest tests/ --collect-only -q | grep -E "skipped|xfail"
```

Пометить @pytest.mark.skip без причины — кандидаты на удаление.

## Чеклист после крупного рефакторинга

Перед коммитом merge-PR:

- [ ] `npx knip` — отчёт пустой (или зафиксирован baseline).
- [ ] `vulture app/ --min-confidence 80` — отчёт пустой.
- [ ] `npm run build` — успешно.
- [ ] `npm run lint` — не выросло количество ошибок.
- [ ] `py -3.10 -m pytest -q` — зелёное.
- [ ] `MISSING:` файлы в CLAUDE.md/AGENTS.md — нет.
- [ ] Список вкладок в CLAUDE.md = реальные `items={[...]}` в коде.
- [ ] Список роутов в CLAUDE.md = реальные `path:` в `routes.tsx`.

## Что делать чтобы Claude меньше ошибался

1. **Доки указывают на источник правды, а не дублируют его.** Вместо «5 tabs — connection, scope, ...» писать «Вкладки — см. [SettingsPage.tsx](src/pages/SettingsPage.tsx)». Если хочется перечислить — добавлять метку «source: file:line».
2. **После переименования/удаления файла — `git grep <старое имя>`** по всему репо. Любое попадание в `*.md` — поправить.
3. **При сокращении функционала (как M10 sync consolidation)** — отдельный коммит «docs: rip stale ... description» в той же PR.
4. **Не оставлять `/foo-old` роуты «на всякий случай».** Удалять сразу — иначе grep по `Foo` уводит в мёртвую страницу.
