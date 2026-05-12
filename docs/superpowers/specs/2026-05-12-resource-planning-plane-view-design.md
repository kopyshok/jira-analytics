# Plane-style view for /resource-planning

**Date:** 2026-05-12
**Status:** Approved by PM (brainstorming dialog 2026-05-12)
**Scope:** Frontend-only visual experiment
**Effort:** 4-5h

## Цель

Дать PM возможность увидеть «вживую» Plane.so-вдохновлённое оформление страницы планирования ресурсов. Мокап `TZ/plane_refs/03_planning.html` понравился — переносим его как параллельный вид внутри текущей страницы, без рисков замены продакшен-вёрстки.

## Контекст

- Текущий `/resource-planning` имеет три вида: Gantt (классика) / List / Heatmap (выбор через AntD `Segmented`)
- Page chrome тёмно-синяя (`DARK_THEME`: bg `#0d1c33`, cyan accent `#00c9c8`)
- В мае 2026 параллельные эксперименты β/γ (PyJobShop + DHTMLX) были выпилены — PM не любит дубли. Поэтому НЕ создаём `/resource-planning-v4`, а добавляем вкладку в существующий компонент

## Решение

### Размещение
Четвёртая кнопка `Plane` в `Segmented` рядом с Gantt / List / Heatmap. Выбор сохраняется в `localStorage` (`rp_view_mode`).

### Что копируем из мокапа
1. **Тёмная Plane-палитра** (адаптированная):
   - Surface: `#ffffff` → `#18181b` (zinc-900)
   - App bg: `#fafafa` → `#09090b` (zinc-950)
   - Borders: `#e4e4e7` → `#27272a` (zinc-800)
   - Text primary: `#18181b` → `#fafafa` (zinc-50)
   - Text secondary: `#71717a` → `#a1a1aa` (zinc-400)
   - Accent: `#6366f1` (indigo-500) — не меняется
   - Role colors: indigo `#6366f1` / emerald `#10b981` / amber `#f59e0b` / violet `#8b5cf6`
2. **Inter font** через Google Fonts (одна `<link>` в `index.html`)
3. **Левый сайдбар 280px** с группами фильтров: Проект / Сотрудник / Роль / Период / Статус (без блока «Сохранённые виды»)
4. **Шапка Plane-стиля**: breadcrumb + название сценария + view-switcher справа
5. **Gantt grid**: скруглённые бары 6px, цвет по роли, тонкие границы, 8px grid, линия «сегодня» indigo пунктир, overload-индикатор красный треугольник слева

### Что НЕ копируем
- Блок «Сохранённые виды» в сайдбаре (мёртвая декорация — пропускаем; будет в фазе B если визуал зайдёт)
- Filter chips bar сверху с активными фильтрами и крестиками (фаза B)
- Замена выбранного дизайна на всё приложение (только эта вкладка)

### Поведение
- Бары кликабельны, открывают тот же `AssignmentSidebar` что и в классическом Gantt — переиспользуем существующее состояние `selectedAssignmentId` и обработчики
- Фильтры в Plane-сайдбаре управляют тем же набором данных что текущая шапка — компоненты разные, источник состояния общий
- Конфликты (`ConflictPanel`), Appearance modal, fork, dependency-draw — не меняем, остаются как в классическом Gantt поверх Plane-grid

### Архитектура файлов
- `frontend/src/components/resource-planning/PlaneGantt.tsx` (новый, ~300 строк) — основной компонент
- `frontend/src/components/resource-planning/PlaneGantt.module.css` (новый) — все Plane-токены
- `frontend/src/components/resource-planning/PlaneSidebar.tsx` (новый, ~150 строк) — левый сайдбар с фильтрами
- `frontend/src/components/resource-planning/GanttRows.ts` — расширить `ViewMode` типом `'plane'`
- `frontend/src/pages/ResourcePlanningPage.tsx` — добавить ветку рендера `viewMode === 'plane'` + сохранить выбор в `localStorage`
- `frontend/index.html` — Google Fonts link на Inter

### Что НЕ трогаем
- `GanttChart`, `ConflictPanel`, `AssignmentSidebar`, `AppearanceModal`, `EmployeeLoadHeatmap` — без изменений
- Логика данных (`useGanttProjection`, `useResourcePlans`, `useEmployees`) — переиспользуется 1:1
- Backend, API, миграции — нет

## Acceptance criteria

1. На `/resource-planning` в `Segmented` четыре кнопки: Gantt / List / Heatmap / Plane
2. При клике на Plane открывается левый сайдбар 280px с группами фильтров и Plane-grid справа
3. Палитра — тёмная Plane (zinc-950 bg, indigo accent), Inter font применяется только внутри Plane-grid (не ломает остальное приложение)
4. Клик по бару открывает `AssignmentSidebar` так же как в классическом Gantt
5. Выбор Plane сохраняется в `localStorage` и восстанавливается при F5
6. Классический Gantt работает без регрессий (manual smoke в браузере)
7. `npm run lint` зелёный
8. Файл `Tcommit + push на main`

## Out of scope (будущие фазы)

- Фаза B: filter chips bar сверху, переключатель на all-app
- Фаза C: «Сохранённые виды» с CRUD + миграция БД
- Фаза D: применение Plane-стиля к List/Heatmap видам тоже

## Открытые риски

- Inter font подгружается извне — если CSP блокирует Google Fonts, придётся положить локально. Проверить при smoke
- AntD `Segmented` в `darkAlgorithm` имеет свой стиль — четвёртая кнопка должна остаться визуально консистентной. Может потребоваться лёгкая правка
