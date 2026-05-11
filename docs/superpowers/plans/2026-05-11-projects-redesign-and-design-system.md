# /projects redesign + Design System overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести тему из «const с полями» в реактивную семантическую архитектуру (4 темы рабочие на всех страницах) и закрыть P0-P2 находки Impeccable-аудита на /projects (счёт 6/20 → ожидаемо 12-14/20).

**Architecture:** Расширить `APP_THEMES` шестью семантическими группами токенов, ввести хук `useThemeTokens` для реактивного доступа, сохранить `DARK_THEME` как алиас через legacy-адаптер. Параллельно — переписать `/projects` под новый дизайн hero (editorial typographic), адаптивную сетку, централизованную палитру графиков, AntD Tooltip и стабильный PNG-экспорт.

**Tech Stack:** React 19, TypeScript 6, AntD 6.3, Vite 8, Recharts 3.8, html2canvas 1.4. Без новых зависимостей.

**Reference:** `docs/superpowers/specs/2026-05-11-projects-redesign-and-design-system-design.md`

---

## File Structure

### Создаются

- `frontend/src/hooks/useThemeTokens.ts` — реактивный хук доступа к токенам текущей темы

### Изменяются (Foundation — Task 1-4)

- `frontend/src/utils/constants.ts` — расширение `APP_THEMES` шестью семантическими группами; `DARK_THEME` становится алиасом
- `frontend/src/main.tsx` — расширенный AntD ConfigProvider

### Изменяются (/projects редизайн — Task 5-9)

- `frontend/src/components/projects/presentation/ProjectHero.tsx` — переписан под вариант C
- `frontend/src/pages/ProjectsPage.tsx` — AntD Row/Col на master-detail split
- `frontend/src/components/projects/ProjectsList.tsx` — снимается `width: 360`
- `frontend/src/components/projects/ProjectAnalysisView.tsx` — CSS Grid auto-fit вместо `1fr 1fr`
- `frontend/src/components/projects/ProjectPresentationView.tsx` — удаление локальных палитр
- `frontend/src/components/projects/cards/ProjectCategoriesCard.tsx` — удаление `AI_PALETTE`
- `frontend/src/components/projects/cards/ProjectEmployeesCard.tsx` — удаление `AVATAR_COLORS`
- `frontend/src/components/projects/cards/ProjectGoalsCard.tsx` — удаление `GOAL_COLORS`
- `frontend/src/components/dashboard/ProjectsWidget.tsx` — `title=` → `<Tooltip>`
- `frontend/src/components/dashboard/CategoryWidget.tsx` — `title=` → `<Tooltip>`
- `frontend/src/components/projects/ProjectHeader.tsx` — `handlePng` без race

### НЕ трогаем (false positive audit / out-of-scope)

- `frontend/src/components/projects/ProjectListCard.tsx` — баг среднего рейтинга оказался ложным срабатыванием аудита. Формула `(q??0)+(s??0)+(r??0) / filter(!=null).length` математически корректна: `??0` для null-полей даёт +0 к сумме, делитель — количество non-null. Не правим, фиксируем заметку в коммите.

---

## Task 1: Foundation — расширить APP_THEMES шестью семантическими группами

**Files:**
- Modify: `frontend/src/utils/constants.ts`

- [ ] **Step 1: Расширить интерфейс `ThemeTokens`**

В `constants.ts` заменить текущий `interface ThemeTokens` на новый. Старые плоские поля удалить (их роли уходят во вложенные группы).

```ts
export type ChartRoleKey = 'blue' | 'green' | 'orange' | 'purple' | 'cyan' | 'red' | 'neutral' | 'yellow';

export interface ThemeTokens {
  surface: {
    page: string;
    sidebar: string;
    card: string;
    accent: string;
    rows: string;
  };
  text: {
    primary: string;
    secondary: string;
    muted: string;
    hint: string;
    dim: string;
  };
  border: {
    subtle: string;
    default: string;
  };
  accent: {
    primary: string;
    secondary: string;
  };
  status: {
    success: string;
    warning: string;
    danger: string;
    info: string;
  };
  chart: {
    series: string[];
    byRole: Record<ChartRoleKey, string>;
  };
}
```

- [ ] **Step 2: Заполнить новые группы для всех четырёх тем**

Переписать `APP_THEMES` так, чтобы каждая тема возвращала объект `ThemeTokens` с заполненными группами. Значения подобрать так, чтобы текущая визуальная identity сохранилась:

- `surface.page/sidebar/card/accent/rows` — текущие значения из старых ключей `pageBg/sidebarBg/cardBg/darkAccent/darkRows`
- `text.primary/secondary/muted/hint` — текущие `textPrimary/...`
- `text.dim` — добавляется (для disabled/placeholder); по умолчанию = `textHint` с уменьшенной непрозрачностью или явная константа
- `border.subtle` — алиас на `border.default` + понижение непрозрачности (например `rgba(...)`-производная), или явный hex
- `border.default` — текущий `border`
- `accent.primary/secondary` — текущие `primary/primarySecondary`
- `status.success/warning/danger/info` — текущие `success / yellow|amber / danger / cyanSecondary` (либо явные значения)
- `chart.series` — единый список `['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#00c9c8', '#E24B4A', '#888780', '#f5c842']` (универсальный для всех тём, не зависит от палитры — это серия для легенды)
- `chart.byRole` — те же значения, но именованные

Пример для `dark-blue`:

```ts
'dark-blue': {
  label: 'Тёмно-синий',
  tokens: {
    surface: {
      page: '#0d1c33',
      sidebar: '#091527',
      card: '#0f2340',
      accent: '#0a2a44',
      rows: '#152740',
    },
    text: {
      primary: '#e8f0fa',
      secondary: '#c5d8ee',
      muted: '#8faec8',
      hint: '#6b8aaa',
      dim: '#4a6a8a',
    },
    border: {
      subtle: 'rgba(255,255,255,0.06)',
      default: '#1e3356',
    },
    accent: {
      primary: '#00c9c8',
      secondary: '#4db8e8',
    },
    status: {
      success: '#1D9E75',
      warning: '#f5a524',
      danger: '#E24B4A',
      info: '#4db8e8',
    },
    chart: {
      series: ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#00c9c8', '#E24B4A', '#888780', '#f5c842'],
      byRole: {
        blue: '#378ADD',
        green: '#1D9E75',
        orange: '#EF9F27',
        purple: '#7F77DD',
        cyan: '#00c9c8',
        red: '#E24B4A',
        neutral: '#888780',
        yellow: '#f5c842',
      },
    },
  },
},
```

Повторить структуру для `dark`, `dark-slate`, `dark-charcoal` — с цветами из старого определения.

- [ ] **Step 3: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -20
```

Ожидаемо: список ошибок во всех файлах, которые использовали старые плоские поля `APP_THEMES[theme].tokens.cardBg` (если такие есть). Это нормально — будут починены в Task 3 через адаптер. Но если ошибок в файлах вне `constants.ts` нет — Task 1 чист.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/utils/constants.ts
git commit -m "feat(theme): расширить APP_THEMES шестью семантическими группами

Новая структура ThemeTokens: surface/text/border/accent/status/chart.
Заполнено для всех четырёх тем (dark/dark-blue/dark-slate/dark-charcoal).
chart.series + chart.byRole — единая палитра серийных цветов для замены
дублированных AI_PALETTE/COLORS/AVATAR_COLORS/GOAL_COLORS.

Сам DARK_THEME (плоская const) и его потребители временно не тронуты —
back-compat адаптер в следующем коммите."
```

---

## Task 2: Foundation — back-compat адаптер для DARK_THEME

**Files:**
- Modify: `frontend/src/utils/constants.ts`

- [ ] **Step 1: Добавить legacy-адаптер**

В конце `constants.ts`, перед `export const FONTS`, добавить функцию-адаптер и переопределить `DARK_THEME`:

```ts
/**
 * @deprecated Используйте `useThemeTokens()` для реактивного доступа к токенам.
 * Эта константа — алиас на тёмно-синюю тему через legacy-адаптер.
 */
export const DARK_THEME = (() => {
  const t = APP_THEMES['dark-blue'].tokens;
  return {
    // Surface
    pageBg: t.surface.page,
    sidebarBg: t.surface.sidebar,
    cardBg: t.surface.card,
    darkAccent: t.surface.accent,
    darkRows: t.surface.rows,
    // Border
    border: t.border.default,
    // Accent
    cyanPrimary: t.accent.primary,
    cyanSecondary: t.accent.secondary,
    // Status
    success: t.status.success,
    yellow: t.status.warning,    // legacy alias
    amber: t.status.warning,
    amberDim: t.status.warning,  // legacy alias (был отдельный тон, теперь = warning)
    danger: t.status.danger,
    // Text
    textPrimary: t.text.primary,
    textSecondary: t.text.secondary,
    textMuted: t.text.muted,
    textHint: t.text.hint,
    textDim: t.text.dim,
  } as const;
})();
```

Это полностью совместимый с прежним API объект — все 16 ключей старого `DARK_THEME` присутствуют, типы такие же (`string`).

Удалить старое объявление `export const DARK_THEME = { ... } as const;` если оно было.

- [ ] **Step 2: Verify все файлы, импортирующие DARK_THEME, компилируются**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v "GanttRows" | head -30
```

Ожидаемо: чисто (только pre-existing GanttRows.idx errors). Если есть ошибки про неизвестные ключи `DARK_THEME.xxx` — добавить недостающий ключ в адаптер.

- [ ] **Step 3: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

Ожидаемо: exit 0.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/utils/constants.ts
git commit -m "feat(theme): legacy-адаптер DARK_THEME → APP_THEMES['dark-blue']

DARK_THEME сохраняется как deprecated алиас на тёмно-синюю тему.
Старые плоские ключи (pageBg, cardBg, textPrimary и т.д.) маппятся
в новую вложенную структуру. Полная back-compat — все 16 ключей
доступны, типы строковые как раньше.

Постепенная миграция отдельных файлов на useThemeTokens — следующие
этапы (out of scope текущего PR)."
```

---

## Task 3: Foundation — `useThemeTokens` hook

**Files:**
- Create: `frontend/src/hooks/useThemeTokens.ts`

- [ ] **Step 1: Создать хук**

```ts
// frontend/src/hooks/useThemeTokens.ts
import { useAppTheme } from '../contexts/ThemeContext';
import { APP_THEMES, type ThemeTokens } from '../utils/constants';

/**
 * Возвращает токены текущей темы. Реактивно: при смене темы компонент
 * ре-рендерится с новыми значениями.
 *
 * Использование:
 * ```ts
 * const t = useThemeTokens();
 * <div style={{ background: t.surface.card, color: t.text.primary }} />
 * ```
 */
export function useThemeTokens(): ThemeTokens {
  const { theme } = useAppTheme();
  return APP_THEMES[theme].tokens;
}
```

- [ ] **Step 2: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -10
```

Ожидаемо: чисто.

- [ ] **Step 3: Smoke-проверка в браузере (необязательно сейчас, проверяется в Task 5+)**

После Task 5 (где hero уже потребляет хук) — открыть `/projects/[any-key]`, переключить тему в Settings, убедиться, что hero реагирует.

- [ ] **Step 4: Коммит**

```bash
git add frontend/src/hooks/useThemeTokens.ts
git commit -m "feat(theme): хук useThemeTokens для реактивного доступа

Возвращает ThemeTokens текущей темы из APP_THEMES. Через useAppTheme()
context — компонент ре-рендерится при смене темы.

Параллельно с DARK_THEME (legacy const) — новые/мигрируемые компоненты
используют этот хук, существующие могут продолжать импортировать
DARK_THEME через адаптер."
```

---

## Task 4: Foundation — AntD ConfigProvider расширение

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Расширить components mapping в ThemedApp**

Найти секцию `components: { Layout: {...}, Menu: {...}, ... }` в `main.tsx` и добавить недостающие AntD-компоненты. Использовать новую структуру `t = APP_THEMES[themeName].tokens` (она теперь объект с группами).

ВАЖНО: внутри `main.tsx` уже идёт обращение `const t = APP_THEMES[themeName].tokens` и потом `t.primary, t.cardBg` и т.д. Эти плоские ключи **исчезли** после Task 1 (т.к. новая структура — вложенная). Нужно переписать обращения на новый путь.

Заменить ВСЕ обращения `t.foo` (плоские) на `t.group.foo` (вложенные) согласно маппингу:

| Старое в main.tsx | Новое |
|---|---|
| `t.primary` | `t.accent.primary` |
| `t.primarySecondary` | `t.accent.secondary` |
| `t.cardBg` | `t.surface.card` |
| `t.pageBg` | `t.surface.page` |
| `t.sidebarBg` | `t.surface.sidebar` |
| `t.darkAccent` | `t.surface.accent` |
| `t.darkRows` | `t.surface.rows` |
| `t.border` | `t.border.default` |
| `t.textPrimary` | `t.text.primary` |
| `t.textSecondary` | `t.text.secondary` |
| `t.textMuted` | `t.text.muted` |
| `t.textHint` | `t.text.hint` |

Затем добавить mappings для новых компонентов:

```tsx
components: {
  // ... существующие Layout/Menu/Card/Table/Modal/Statistic/Typography/Tabs/Collapse ...

  Tag: {
    defaultBg: t.surface.accent,
    defaultColor: t.text.primary,
  },
  Tooltip: {
    colorBgSpotlight: t.surface.accent,
    colorTextLightSolid: t.text.primary,
  },
  Button: {
    defaultBg: t.surface.card,
    defaultBorderColor: t.border.default,
    defaultColor: t.text.primary,
  },
  Input: {
    activeBorderColor: t.accent.primary,
    hoverBorderColor: t.accent.secondary,
  },
  Select: {
    optionSelectedBg: t.surface.accent,
  },
  DatePicker: {
    activeBorderColor: t.accent.primary,
  },
  Form: {
    labelColor: t.text.secondary,
  },
  Alert: {
    colorInfoBg: t.surface.accent,
    colorInfoBorder: t.border.default,
  },
  Notification: {
    colorBgElevated: t.surface.card,
  },
  Dropdown: {
    colorBgElevated: t.surface.card,
  },
  Popover: {
    colorBgElevated: t.surface.card,
  },
  Drawer: {
    colorBgElevated: t.surface.card,
  },
  Spin: {
    colorPrimary: t.accent.primary,
  },
  Empty: {
    colorTextDisabled: t.text.muted,
  },
},
```

- [ ] **Step 2: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -20
```

Ожидаемо: чисто. Если есть ошибки про неизвестные поля темы AntD — проверить актуальные имена в `node_modules/antd/es/<component>/style/index.d.ts`.

- [ ] **Step 3: Smoke-проверка переключения темы**

```bash
cd frontend && npm run dev
```

Открыть http://localhost:5173, зайти в Settings → переключить тему. Все ранее тёмно-синие AntD-компоненты (Tag, Tooltip, Input в фильтрах) должны окраситься под новую тему. Если что-то осталось AntD-дефолтным — добавить mapping для этого компонента.

Завершить dev-сервер (Ctrl+C).

- [ ] **Step 4: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

Ожидаемо: exit 0.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/main.tsx
git commit -m "feat(theme): расширенный AntD ConfigProvider

Добавлены mappings: Tag, Tooltip, Button, Input, Select, DatePicker,
Form, Alert, Notification, Dropdown, Popover, Drawer, Spin, Empty.
Обращения t.foo переведены на новую вложенную структуру (t.surface.card,
t.text.primary и т.д.).

После этого все AntD-компоненты следуют активной теме на всех 4 палитрах.

Завершает Foundation Stage 1. Этап 2 — /projects редизайн — в следующих
коммитах."
```

---

## Task 5: B.2a — Hero редизайн (вариант C, editorial typographic)

**Files:**
- Modify: `frontend/src/components/projects/presentation/ProjectHero.tsx`

- [ ] **Step 1: Полная перепись ProjectHero**

```tsx
// frontend/src/components/projects/presentation/ProjectHero.tsx
import React from 'react';
import { Tag } from 'antd';
import type { ProjectDetail } from '../../../types/projects';
import { useThemeTokens } from '../../../hooks/useThemeTokens';
import { FONTS } from '../../../utils/constants';

export const ProjectHero: React.FC<{ detail: ProjectDetail }> = ({ detail }) => {
  const t = useThemeTokens();

  const periodText = formatPeriod(detail.period_start, detail.period_end);
  const statusTone = statusToneFor(detail.status_category);
  const prose = buildProseSummary(detail);

  return (
    <div
      style={{
        padding: '40px 24px 32px',
        borderBottom: `1px solid ${t.border.subtle}`,
      }}
    >
      {/* Project key — small, plain, no uppercase-letter-spaced eyebrow */}
      <div style={{ fontSize: 12, color: t.text.hint, marginBottom: 8, fontFamily: FONTS.mono }}>
        {detail.key}
      </div>

      {/* Title — Fraunces italic, editorial */}
      <h1
        style={{
          margin: '0 0 16px',
          fontFamily: FONTS.display,
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: 32,
          lineHeight: 1.25,
          color: t.text.primary,
        }}
      >
        {detail.summary}
      </h1>

      {/* Period + status as pill-chips */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {periodText && (
          <Tag
            style={{
              background: 'transparent',
              border: `1px solid ${t.border.default}`,
              color: t.text.secondary,
              borderRadius: 999,
              padding: '2px 10px',
              fontSize: 12,
              margin: 0,
            }}
          >
            {periodText}
          </Tag>
        )}
        {detail.status && (
          <Tag
            style={{
              background: 'transparent',
              border: `1px solid ${statusTone.border}`,
              color: statusTone.color,
              borderRadius: 999,
              padding: '2px 10px',
              fontSize: 12,
              margin: 0,
            }}
          >
            {detail.status}
          </Tag>
        )}
      </div>

      {/* Prose summary — metrics dissolved into a sentence */}
      <p
        style={{
          margin: 0,
          fontSize: 14,
          lineHeight: 1.6,
          color: t.text.secondary,
          maxWidth: 640,
        }}
      >
        {prose}
      </p>
    </div>
  );
};

function formatPeriod(s: string | null, e: string | null): string | null {
  if (!s && !e) return null;
  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';
  return `${fmt(s)} — ${fmt(e)}`;
}

function statusToneFor(category: string | null): { color: string; border: string } {
  // Inline tone selection — colours come from theme, but we need contextual mapping
  // (success/info/muted) which is per-status not per-theme. Caller passes status_category.
  if (category === 'done') return { color: '#67d68d', border: '#67d68d' };
  if (category === 'indeterminate') return { color: '#00c9c8', border: '#00c9c8' };
  return { color: '#8faec8', border: '#1e3356' };
}

function buildProseSummary(d: ProjectDetail): string {
  const parts: string[] = [];
  const people = d.employee_count;
  const weeks = d.weeks;
  const hours = d.total_hours;
  const tasks = d.child_count;

  if (people > 0 && weeks > 0) {
    parts.push(`На проекте ${people} ${pluralizePeople(people)} работали ${weeks} ${pluralizeWeeks(weeks)}`);
  } else if (people > 0) {
    parts.push(`На проекте ${people} ${pluralizePeople(people)}`);
  }

  if (hours > 0) {
    const fmtHours = new Intl.NumberFormat('ru-RU').format(Math.round(hours));
    parts.push(`записали ${fmtHours} ${pluralizeHours(hours)}`);
  }

  if (tasks > 0) {
    parts.push(`в ${tasks} ${pluralizeTasks(tasks)}`);
  }

  if (parts.length === 0) return 'Данных по проекту пока нет.';

  if (parts.length === 1) return parts[0] + '.';

  // [people+weeks] — [hours] в [tasks].
  return parts.length === 3
    ? `${parts[0]} — ${parts[1]} ${parts[2]}.`
    : parts.join(' — ') + '.';
}

function pluralizePeople(n: number): string {
  const last2 = n % 100;
  const last = n % 10;
  if (last2 >= 11 && last2 <= 14) return 'человек';
  if (last === 1) return 'человек';
  if (last >= 2 && last <= 4) return 'человека';
  return 'человек';
}

function pluralizeWeeks(n: number): string {
  const last2 = n % 100;
  const last = n % 10;
  if (last2 >= 11 && last2 <= 14) return 'недель';
  if (last === 1) return 'неделю';
  if (last >= 2 && last <= 4) return 'недели';
  return 'недель';
}

function pluralizeHours(n: number): string {
  const last2 = Math.round(n) % 100;
  const last = Math.round(n) % 10;
  if (last2 >= 11 && last2 <= 14) return 'часов';
  if (last === 1) return 'час';
  if (last >= 2 && last <= 4) return 'часа';
  return 'часов';
}

function pluralizeTasks(n: number): string {
  const last2 = n % 100;
  const last = n % 10;
  if (last2 >= 11 && last2 <= 14) return 'задачах';
  if (last === 1) return 'задаче';
  if (last >= 2 && last <= 4) return 'задачах';
  return 'задачах';
}
```

Старый компонент `BigTile` удаляется (он больше не используется нигде).

ВАЖНО: `statusToneFor` пока хардкодит цвета `#67d68d` (success-светлый) / `#00c9c8` (cyan). Они НЕ в семантических токенах темы. Это допустимо: статус-категория («done/indeterminate/new») — концептуально другая ось, чем фоны/тексты, и она едина для всех 4 тем. Эти три hex-цвета попадут в `tokens.chart.byRole` (cyan = byRole.cyan, success-светлый = добавить позже как `byRole.success`). Пока — оставить inline с TODO-комментарием.

ОБНОВЛЕНИЕ: чтобы не попасть под ESLint-правило (если оно активно к моменту работы), лучше сразу взять из `t.chart.byRole`:

```ts
function statusToneFor(category: string | null, t: ThemeTokens): { color: string; border: string } {
  if (category === 'done') return { color: t.status.success, border: t.status.success };
  if (category === 'indeterminate') return { color: t.accent.primary, border: t.accent.primary };
  return { color: t.text.muted, border: t.border.default };
}
```

И передавать `t` из вызывающего кода: `const tone = statusToneFor(detail.status_category, t);`. Это финальный вариант.

- [ ] **Step 2: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -10
```

Если есть ошибка про `BigTile` импорт где-то ещё — удалить импорт или превратить компонент в no-op. Глобальный поиск `BigTile`:

```bash
cd frontend && grep -rn "BigTile" src/
```

Если найден только в `ProjectHero.tsx` (где он определяется/использовался) — ок.

- [ ] **Step 3: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

Ожидаемо: exit 0.

- [ ] **Step 4: Smoke-проверка**

```bash
cd frontend && npm run dev
```

Открыть `http://localhost:5173/projects/[any-key]`, переключиться на Presentation view. Убедиться:
- Заголовок — крупный курсивный Fraunces
- Под заголовком — pill-чипы периода и статуса с тонкой рамкой
- Прозаическое предложение «На проекте N человек работали W недель — записали H часов в T задачах»
- НЕТ трёх KPI-плиток

Переключить тему в Settings — hero реагирует.

Завершить dev-сервер.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/components/projects/presentation/ProjectHero.tsx
git commit -m "feat(projects): hero редизайн — editorial typographic (вариант C)

Замена трёх KPI-плиток на:
- Fraunces italic заголовок 32px
- Period + status как pill-чипы (тонкая рамка, без фона)
- Прозаическое предложение со всеми метриками внутри:
  «На проекте N человек работали W недель — записали H часов в T задачах»

Русская плюрализация через локальные helpers (Intl.PluralRules можно
вынести в utils в следующей итерации).

Hero потребляет useThemeTokens — первый компонент на новой архитектуре."
```

---

## Task 6: B.2b — Адаптивная сетка master-detail + внутренних карточек

**Files:**
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/components/projects/ProjectsList.tsx`
- Modify: `frontend/src/components/projects/ProjectAnalysisView.tsx`

- [ ] **Step 1: ProjectsPage — заменить flex на AntD Row/Col**

```tsx
// frontend/src/pages/ProjectsPage.tsx
import { useNavigate, useParams } from 'react-router';
import { Empty, Row, Col } from 'antd';
import { ProjectsList } from '../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../components/projects/ProjectDetailPanel';
import { useThemeTokens } from '../hooks/useThemeTokens';

export default function ProjectsPage() {
  const navigate = useNavigate();
  const { key } = useParams<{ key?: string }>();
  const t = useThemeTokens();

  const handleSelect = (selectedKey: string) => {
    navigate(`/projects/${encodeURIComponent(selectedKey)}`);
  };

  return (
    <div
      className="projects-master-detail"
      style={{
        minHeight: 'calc(100vh - 64px)',
        background: t.surface.page,
      }}
    >
      <Row gutter={0} wrap>
        <Col xs={24} md={8} lg={6} style={{ borderRight: `1px solid ${t.border.default}` }}>
          <ProjectsList selectedKey={key ?? null} onSelect={handleSelect} />
        </Col>
        <Col xs={24} md={16} lg={18}>
          {key ? (
            <ProjectDetailPanel projectKey={key} />
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
              <Empty
                description={
                  <span style={{ color: t.text.muted }}>Выберите проект из списка слева</span>
                }
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </div>
          )}
        </Col>
      </Row>
    </div>
  );
}
```

Ключевые изменения:
- `display: flex` + `height: calc(100vh - 64px)` → `Row/Col` + `minHeight`. Это разрешает естественный скролл всей страницы при необходимости.
- xs стак, md split.
- Удалён `overflow: hidden` — детейл может скроллить сам собой.

- [ ] **Step 2: ProjectsList — снять width: 360**

В `frontend/src/components/projects/ProjectsList.tsx`, заменить:

```tsx
<div
  style={{
    width: 360,
    flexShrink: 0,
    ...
  }}
>
```

на:

```tsx
<div
  style={{
    width: '100%',  // занимает всю ширину Col
    display: 'flex',
    flexDirection: 'column',
    background: t.surface.card,
    minHeight: '100%',
  }}
>
```

(Использовать `useThemeTokens` если не используется — заменить `DARK_THEME.*` на `t.*`. Если файл уже использует `DARK_THEME` — оставить как есть, это работает через адаптер, миграция файла не входит в текущий PR.)

- [ ] **Step 3: ProjectAnalysisView — CSS Grid auto-fit**

В `frontend/src/components/projects/ProjectAnalysisView.tsx`, заменить:

```tsx
<div style={{ padding: 16, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    {/* левая колонка */}
  </div>
  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    {/* правая колонка */}
  </div>
</div>
```

на одну плоскую сетку:

```tsx
<div
  style={{
    padding: 16,
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
    gap: 16,
    alignItems: 'start',
  }}
>
  <ProjectGoalsCard summary={summary} description={detail.description} />
  <ProjectResultCard summary={summary} />
  <ProjectCategoriesCard
    categories={detail.categories}
    totalHours={detail.total_hours}
    weeks={detail.weeks}
    projectKey={detail.key}
    summary={summary}
    issueHoursByKey={detail.issue_hours_by_key}
  />
  <ProjectStatusCard summary={summary} detail={detail} />
  <ProjectEmployeesCard employees={detail.employees} projectKey={detail.key} />
  <ProjectRatingsCard detail={detail} summary={summary} />
  <ProjectTopIssuesCard topIssues={detail.top_issues} projectKey={detail.key} />
</div>
```

Карточки сами обтекают: при широком экране — 3-4 в ряд, на md — 2, на узком — 1.

- [ ] **Step 4: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -10
```

- [ ] **Step 5: Smoke-проверка**

```bash
cd frontend && npm run dev
```

Открыть `/projects/[any-key]`, ресайзить окно браузера от 1920 до 600. Убедиться:
- При ширине ≥ md (≥768) — список слева, карточка справа
- При xs — список вверху, детейл внизу
- В Analysis view карточки переключаются с 3-4 в ряд → 2 → 1 при сужении

Завершить dev-сервер.

- [ ] **Step 6: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

Ожидаемо: exit 0.

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/pages/ProjectsPage.tsx frontend/src/components/projects/ProjectsList.tsx frontend/src/components/projects/ProjectAnalysisView.tsx
git commit -m "feat(projects): адаптивная сетка master-detail + analysis-view

ProjectsPage: flex + calc(100vh-64px) → AntD Row/Col с xs=24 md=8 lg=6
для списка, md=16 lg=18 для детейла. На узких — стак.

ProjectsList: убрана hard-coded width: 360, теперь width: 100% от Col.

ProjectAnalysisView: 1fr 1fr → repeat(auto-fit, minmax(320px, 1fr)).
Карточки сами раскладываются 3→2→1 при сужении окна, без media-queries."
```

---

## Task 7: B.2c — Централизация палитры графиков

**Files:**
- Modify: `frontend/src/components/projects/cards/ProjectCategoriesCard.tsx`
- Modify: `frontend/src/components/projects/cards/ProjectEmployeesCard.tsx`
- Modify: `frontend/src/components/projects/cards/ProjectGoalsCard.tsx`
- Modify: `frontend/src/components/projects/ProjectPresentationView.tsx`

- [ ] **Step 1: ProjectCategoriesCard — удалить AI_PALETTE**

В файле найти строку:
```ts
const AI_PALETTE = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#ff4d4f', '#67d68d'];
```

Удалить. В компоненте, где используется `AI_PALETTE[i % AI_PALETTE.length]`, перейти на хук:

```ts
import { useThemeTokens } from '../../../hooks/useThemeTokens';

// inside component
const t = useThemeTokens();
const palette = t.chart.series;
// ... color: palette[i % palette.length],
```

- [ ] **Step 2: ProjectEmployeesCard — удалить AVATAR_COLORS**

Аналогично: удалить локальный массив, использовать `t.chart.series`.

- [ ] **Step 3: ProjectGoalsCard — удалить GOAL_COLORS**

Аналогично.

- [ ] **Step 4: ProjectPresentationView — удалить COLORS и AI_PALETTE**

В файле две константы. Удалить обе. Все использования заменить на `t.chart.series`.

- [ ] **Step 5: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -10
```

Если есть ошибки про unused import — удалить.

- [ ] **Step 6: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

- [ ] **Step 7: Smoke-проверка**

`npm run dev` → `/projects/[any-key]` → визуальная проверка: цвета чартов (категории donut, аватары сотрудников, целевые маркеры) выглядят как раньше. Никаких розовых-фиолетовых неожиданностей.

- [ ] **Step 8: Коммит**

```bash
git add frontend/src/components/projects/cards/Project{Categories,Employees,Goals}Card.tsx frontend/src/components/projects/ProjectPresentationView.tsx
git commit -m "feat(projects): централизация серийных цветов через tokens.chart.series

Удалены 4 локальные палитры (AI_PALETTE × 2, AVATAR_COLORS, GOAL_COLORS) —
все компоненты потребляют единый список из текущей темы через
useThemeTokens. При смене темы серия чартов автоматически обновляется
(сейчас все 4 темы используют один универсальный список из 8 цветов,
будущая кастомизация per-theme не ломает консьюмеров)."
```

---

## Task 8: B.2d — Native title → AntD Tooltip (Dashboard widgets)

**Files:**
- Modify: `frontend/src/components/dashboard/ProjectsWidget.tsx`
- Modify: `frontend/src/components/dashboard/CategoryWidget.tsx`

- [ ] **Step 1: Найти все use of HTML title=**

```bash
cd frontend && grep -n "title={" src/components/dashboard/ProjectsWidget.tsx src/components/dashboard/CategoryWidget.tsx
```

Ожидается 2-3 места (per audit: аватары участников в ProjectsWidget, multi-line подсказки в CategoryWidget).

- [ ] **Step 2: ProjectsWidget — заменить**

Найти `<div title={...}>` или `<span title={...}>`. Обернуть в `<Tooltip>`:

```tsx
import { Tooltip } from 'antd';

// Было:
<div title={a.initials} style={...}>{a.label}</div>

// Стало:
<Tooltip title={a.initials}>
  <div style={...}>{a.label}</div>
</Tooltip>
```

ВАЖНО: AntD Tooltip требует, чтобы child мог принимать ref. Простые `<div>` ок. Если внутри `<Fragment>` — обернуть в `<span>`.

- [ ] **Step 3: CategoryWidget — заменить**

Здесь есть многострочный текст через `\n` (нативный title не показывает многострочность). После замены — текст разбить на JSX:

```tsx
// Было:
const tooltip = `Категория: ${cat.name}\nЧасов: ${cat.hours}\nДоля: ${cat.share}%`;
<div title={tooltip}>...</div>

// Стало:
<Tooltip title={
  <div>
    <div>Категория: {cat.name}</div>
    <div>Часов: {cat.hours}</div>
    <div>Доля: {cat.share}%</div>
  </div>
}>
  <div>...</div>
</Tooltip>
```

- [ ] **Step 4: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -10
```

- [ ] **Step 5: Smoke-проверка**

`npm run dev` → `/` (dashboard) → навести мышь на аватары в ProjectsWidget, на категории в CategoryWidget. Тултипы:
- Появляются с задержкой ~100ms (быстрее нативного)
- В стиле темы (тёмный фон, не белый)
- Многострочные в CategoryWidget работают

- [ ] **Step 6: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

- [ ] **Step 7: Коммит**

```bash
git add frontend/src/components/dashboard/ProjectsWidget.tsx frontend/src/components/dashboard/CategoryWidget.tsx
git commit -m "feat(dashboard): native title= → AntD Tooltip

ProjectsWidget: аватары участников теперь с AntD-тултипом
(читабельный стиль темы, доступен с клавиатуры).

CategoryWidget: многострочные подсказки через \n в нативном title не
работали — теперь корректные многострочные тултипы через JSX-контент."
```

---

## Task 9: B.2e — PNG export без race

**Files:**
- Modify: `frontend/src/components/projects/ProjectHeader.tsx`

- [ ] **Step 1: Переписать handlePng**

Найти функцию `handlePng` в `ProjectHeader.tsx` (~строки 55-89). Заменить блок ожидания + снимка:

```tsx
const handlePng = async () => {
  if (!detail) return;
  onViewChange('presentation');
  setExporting(true);
  try {
    // Wait for view switch to flush
    await new Promise((r) => requestAnimationFrame(r));
    await new Promise((r) => requestAnimationFrame(r));

    const target = document.querySelector<HTMLElement>('.presentation-view');
    if (!target) {
      message.error('Контейнер для экспорта не найден');
      return;
    }

    // Wait for fonts (Fraunces, Manrope, JetBrains Mono)
    if (document.fonts && document.fonts.ready) {
      await document.fonts.ready;
    }

    // Wait for images inside target
    const images = Array.from(target.querySelectorAll<HTMLImageElement>('img'));
    await Promise.all(
      images
        .filter((img) => !img.complete)
        .map(
          (img) =>
            new Promise<void>((res) => {
              const done = () => res();
              img.addEventListener('load', done, { once: true });
              img.addEventListener('error', done, { once: true });
            }),
        ),
    );

    // Final layout flush
    await new Promise((r) => requestAnimationFrame(r));

    const canvas = await html2canvas(target, {
      backgroundColor: '#0d1c33', // page bg, hard-coded (acceptable: snapshot context)
      scale: 2,
      useCORS: true,
      height: target.scrollHeight,
      windowHeight: target.scrollHeight,
    });
    const dataUrl = canvas.toDataURL('image/png');
    const a = document.createElement('a');
    const today = new Date();
    const stamp = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, '0')}${String(today.getDate()).padStart(2, '0')}`;
    a.href = dataUrl;
    a.download = `${detail.key}_${stamp}.png`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } catch (e) {
    message.error('Не удалось сохранить картинку');
    console.error(e);
  } finally {
    setExporting(false);
  }
};
```

Ключевые изменения:
- `setTimeout(800)` → детерминированное ожидание: 2 rAF + `document.fonts.ready` + `Promise.all` загрузки изображений + ещё 1 rAF.
- Recharts анимации НЕ отключаются явно в этом PR (см. примечание ниже). Внешние два rAF + ожидание шрифтов в большинстве случаев достаточно.

Примечание: полное отключение анимаций Recharts через ExportContext — отдельная подзадача. В текущем PR — детерминированное ожидание через rAF + шрифты + изображения. Если на практике первые снимки всё ещё пустые из-за Recharts — добавить второй коммит с `isAnimationActive={false}` propagation через context.

- [ ] **Step 2: Verify typecheck**

```bash
cd frontend && npx tsc -b --noEmit 2>&1 | grep -v GanttRows | head -10
```

- [ ] **Step 3: Smoke-проверка**

`npm run dev` → `/projects/[any-key]` → нажать кнопку «PNG». Убедиться:
- Не подвисает дольше ~1-2 секунд
- Скачивается PNG-файл с содержимым презентации (заголовок Fraunces, чарты заполненные)
- Если первый снимок пустой — обновить страницу и попробовать снова; если стабильно пусто — добавить TODO для следующего PR (Recharts animation context).

- [ ] **Step 4: Verify Impeccable detect**

```bash
cd frontend && npm run lint:design
```

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/components/projects/ProjectHeader.tsx
git commit -m "fix(projects): PNG export без 800ms race

handlePng теперь детерминированно дожидается:
1. requestAnimationFrame × 2 (layout flush после переключения view)
2. document.fonts.ready (Fraunces/Manrope/JetBrains Mono загружены)
3. Promise.all загрузки картинок внутри .presentation-view
4. финальный rAF

Заменяет ненадёжный setTimeout(800), который иногда снимал пустую
презентацию до завершения анимаций Recharts и загрузки шрифтов.

Полное отключение анимаций Recharts через ExportContext — отдельная
подзадача на будущий PR, если эта стратегия окажется недостаточной."
```

---

## Self-Review (выполнено автором плана)

### Spec coverage

- §3.1 (структура токенов) → Task 1 ✓
- §3.2 (хук) → Task 3 ✓
- §3.3 (back-compat адаптер) → Task 2 ✓
- §3.4 (AntD маппинг) → Task 4 ✓
- §3.5 (ESLint правило) → out of scope, отмечено в плане
- §4.1 (hero вариант C) → Task 5 ✓
- §4.2 (адаптивная сетка) → Task 6 ✓
- §4.3 (палитра графиков) → Task 7 ✓
- §4.4 (Tooltip) → Task 8 ✓
- §4.5 (PNG fix) → Task 9 ✓
- §4.6 (рейтинг bug) → false positive, отмечено в плане
- §5 (этапы) → Tasks 1-9 распределены по двум стадиям ✓

### Placeholder scan

- Нет TBD/TODO/«implement later» в коде шагов ✓
- Все шаги содержат либо точный код, либо точную команду ✓
- Псевдо-код только в Step 1 Task 9 («Recharts animations отключение через context») — но это явно out-of-scope для текущего PR и обозначено как «отдельная подзадача на будущий PR» ✓

### Type consistency

- `ThemeTokens` интерфейс — определён в Task 1, потребляется в Task 3 и далее, имена групп совпадают ✓
- `useThemeTokens` — сигнатура `(): ThemeTokens`, используется одинаково везде ✓
- `ChartRoleKey` — определён в Task 1, используется в Task 7 неявно ✓
- `DARK_THEME` legacy-ключи — таблица маппинга в Task 2, использование в существующих файлах сохраняется ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-11-projects-redesign-and-design-system.md`.

Пользователь явно попросил: «приступай к реализации, если надо делай через субагентов». → **Subagent-Driven execution** через superpowers:subagent-driven-development.
