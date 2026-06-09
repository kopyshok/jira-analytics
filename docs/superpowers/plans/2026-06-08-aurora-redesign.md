# Aurora Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Полный визуальный редизайн фронта под «Aurora» (glass + cyan→violet gradient, dark/light). Сохранить структуру форм и функциональность 1:1. Переключение classic ↔ aurora-dark ↔ aurora-light глобальной кнопкой в шапке, persisted per-user.

**Architecture:** Расширяем существующую тему-инфру (`User.selected_theme`, `useThemeSync/useSaveTheme`, `ThemeProvider`) — добавляем два новых значения `aurora-dark` и `aurora-light`. На корне DOM выставляем `data-theme=aurora` + `data-mode=dark|light`. Aurora-режим использует свой shell (`AuroraShell` вместо `AppLayout`), свои примитивы (`GlassCard/Button/Pill/...`), и overlay `antdGlass.css` для нативных AntD-компонентов внутри форм. Классика остаётся нетронутой.

**Tech Stack:** React 19 + TS 6 + Vite 8 + AntD 6 + TanStack Query + Recharts. Новые зависимости: `lucide-react`, `@fontsource/fraunces`, `@fontsource/manrope`, `@fontsource/jetbrains-mono`.

**Ветка:** `redesign/aurora` (создана). Спека: [`docs/superpowers/specs/2026-06-08-aurora-redesign-design.md`](../specs/2026-06-08-aurora-redesign-design.md).

**Команды:**
- backend tests: `py -3.10 -m pytest tests/ -v`
- frontend dev: `cd frontend && npm run dev` (порт :5173)
- frontend lint: `cd frontend && npm run lint`
- frontend build: `cd frontend && npm run build`
- backend reload Windows: убить PID на :8000, запустить заново (uvicorn --reload зависает)

---

## Phase 1 — Theme infrastructure (extend existing)

### Task 1: Расширить тип AppTheme — добавить aurora-dark / aurora-light

**Files:**
- Modify: `frontend/src/utils/constants.ts:59` (тип `AppTheme`)
- Modify: `frontend/src/utils/constants.ts:76-145` (`APP_THEMES`)
- Modify: `frontend/src/contexts/ThemeContext.tsx:17` (валидация в `readStoredTheme`)
- Test: `frontend/src/utils/__tests__/constants.test.ts` (новый)

- [ ] **Step 1: Write the failing test**

`frontend/src/utils/__tests__/constants.test.ts`:
```typescript
import { describe, it, expect } from 'vitest';
import { APP_THEMES, type AppTheme } from '../constants';

describe('APP_THEMES Aurora', () => {
  it('includes aurora-dark and aurora-light', () => {
    expect(APP_THEMES['aurora-dark']).toBeDefined();
    expect(APP_THEMES['aurora-light']).toBeDefined();
  });

  it('aurora-dark uses cyan→violet accents', () => {
    expect(APP_THEMES['aurora-dark'].tokens.primary).toBe('#38bdf8');
    expect(APP_THEMES['aurora-dark'].tokens.primarySecondary).toBe('#a78bfa');
  });

  it('aurora-light is the inverted variant', () => {
    expect(APP_THEMES['aurora-light'].tokens.pageBg).toBe('#eef2fb');
    expect(APP_THEMES['aurora-light'].tokens.primary).toBe('#0ea5e9');
  });

  it('AppTheme union includes both Aurora values', () => {
    const themes: AppTheme[] = ['dark', 'dark-blue', 'dark-slate', 'dark-charcoal', 'aurora-dark', 'aurora-light'];
    expect(themes).toHaveLength(6);
  });
});
```

- [ ] **Step 2: Run the test — FAIL**

```bash
cd frontend && npm test -- constants.test.ts
```
Expected: FAIL (`APP_THEMES['aurora-dark']` is undefined).

- [ ] **Step 3: Extend the type union**

`frontend/src/utils/constants.ts` line 59:
```typescript
export type AppTheme = 'dark' | 'dark-blue' | 'dark-slate' | 'dark-charcoal' | 'aurora-dark' | 'aurora-light';
```

- [ ] **Step 4: Add Aurora entries to `APP_THEMES`**

`frontend/src/utils/constants.ts` — добавить два новых ключа в объект `APP_THEMES` (после `'dark-charcoal'`):
```typescript
  'aurora-dark': {
    label: 'Aurora тёмная',
    tokens: {
      pageBg: '#080b16',
      sidebarBg: '#0d1226',
      cardBg: 'rgba(255,255,255,0.045)',
      darkAccent: 'rgba(255,255,255,0.06)',
      border: 'rgba(255,255,255,0.10)',
      darkRows: 'rgba(255,255,255,0.025)',
      primary: '#38bdf8',
      primarySecondary: '#a78bfa',
      textPrimary: '#eaf0fb',
      textSecondary: '#b8c6e0',
      textMuted: '#7f90b0',
      textHint: '#5a6a85',
    },
  },
  'aurora-light': {
    label: 'Aurora светлая',
    tokens: {
      pageBg: '#eef2fb',
      sidebarBg: 'rgba(255,255,255,0.55)',
      cardBg: 'rgba(255,255,255,0.55)',
      darkAccent: 'rgba(255,255,255,0.75)',
      border: 'rgba(255,255,255,0.85)',
      darkRows: 'rgba(255,255,255,0.4)',
      primary: '#0ea5e9',
      primarySecondary: '#7c5cf6',
      textPrimary: '#16203a',
      textSecondary: '#3f4d6e',
      textMuted: '#707f9e',
      textHint: '#8b97b3',
    },
  },
```

- [ ] **Step 5: Update `readStoredTheme` validation**

`frontend/src/contexts/ThemeContext.tsx` lines 15-20:
```typescript
function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (
      v === 'dark-blue' ||
      v === 'dark-slate' ||
      v === 'dark-charcoal' ||
      v === 'dark' ||
      v === 'aurora-dark' ||
      v === 'aurora-light'
    ) return v;
  } catch {
    // localStorage unavailable
  }
  return 'aurora-dark';
}
```
Note: дефолт меняется с `dark-blue` на `aurora-dark` (anonymous landing на /login увидит Aurora).

- [ ] **Step 6: Run the test — PASS**

```bash
cd frontend && npm test -- constants.test.ts
```
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/utils/constants.ts frontend/src/contexts/ThemeContext.tsx frontend/src/utils/__tests__/constants.test.ts
git commit -m "feat(aurora): добавлены темы aurora-dark и aurora-light в APP_THEMES"
```

---

### Task 2: Бэкенд — расширить валидацию `selected_theme`

**Files:**
- Check: `app/api/endpoints/users.py` (где валидируется поле в `PUT /users/me/theme`)
- Test: `tests/api/test_user_theme.py` (новый или существующий)

- [ ] **Step 1: Найти текущий endpoint валидации**

```bash
rg "selected_theme|/me/theme" app/api/ --type py
```
Найти Pydantic-схему которая валидирует `theme` поле.

- [ ] **Step 2: Write failing test**

`tests/api/test_user_theme.py`:
```python
import pytest
from fastapi.testclient import TestClient

@pytest.mark.parametrize("theme", ["aurora-dark", "aurora-light"])
def test_can_set_aurora_theme(authed_client: TestClient, theme: str):
    res = authed_client.put("/api/v1/users/me/theme", json={"theme": theme})
    assert res.status_code == 200

    me = authed_client.get("/api/v1/auth/me").json()
    assert me["selected_theme"] == theme

def test_rejects_unknown_theme(authed_client: TestClient):
    res = authed_client.put("/api/v1/users/me/theme", json={"theme": "neon-pink"})
    assert res.status_code == 422
```

- [ ] **Step 3: Run test — FAIL**

```bash
py -3.10 -m pytest tests/api/test_user_theme.py -v
```
Expected: FAIL (если валидация enum — 422 на aurora-dark; если без — пройдёт но без enum-защиты).

- [ ] **Step 4: Расширить enum / Literal в Pydantic схеме**

Открыть найденный модуль (вероятно `app/schemas/user.py` или внутри `app/api/endpoints/users.py`). Найти `Literal['dark', 'dark-blue', 'dark-slate', 'dark-charcoal']` или enum. Расширить:
```python
ThemeName = Literal['dark', 'dark-blue', 'dark-slate', 'dark-charcoal', 'aurora-dark', 'aurora-light']
```

- [ ] **Step 5: Run test — PASS**

```bash
py -3.10 -m pytest tests/api/test_user_theme.py -v
```
Expected: PASS оба теста.

- [ ] **Step 6: Restart backend (Windows)**

Убить PID на :8000, перезапустить:
```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess | ForEach-Object { Stop-Process -Id $_ -Force }
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 7: Commit**

```bash
git add app/ tests/api/test_user_theme.py
git commit -m "feat(aurora): backend принимает aurora-dark/aurora-light в PUT /users/me/theme"
```

---

### Task 3: Установить npm-зависимости (Lucide + Fontsource)

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Install**

```bash
cd frontend && npm install lucide-react @fontsource/fraunces @fontsource/manrope @fontsource/jetbrains-mono
```

- [ ] **Step 2: Verify build still works**

```bash
cd frontend && npm run build
```
Expected: PASS, no warnings about missing modules.

- [ ] **Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "feat(aurora): добавлены зависимости lucide-react + fontsource шрифты"
```

---

### Task 4: Скопировать Aurora CSS-файлы из reference

**Files:**
- Create: `frontend/src/aurora/styles/fonts.css`
- Create: `frontend/src/aurora/styles/glass.css`
- Create: `frontend/src/aurora/styles/app.css`
- Create: `frontend/src/aurora/styles/antdGlass.css`
- Create: `frontend/src/aurora/styles/aurora.css` (entry point)

- [ ] **Step 1: Create `fonts.css`**

`frontend/src/aurora/styles/fonts.css`:
```css
@import '@fontsource/fraunces/400.css';
@import '@fontsource/fraunces/500.css';
@import '@fontsource/fraunces/600.css';
@import '@fontsource/manrope/400.css';
@import '@fontsource/manrope/500.css';
@import '@fontsource/manrope/600.css';
@import '@fontsource/manrope/700.css';
@import '@fontsource/jetbrains-mono/400.css';
@import '@fontsource/jetbrains-mono/500.css';
@import '@fontsource/jetbrains-mono/700.css';
```

- [ ] **Step 2: Create `glass.css`**

Скопировать содержимое `design-reference/redesign/glass.css` в `frontend/src/aurora/styles/glass.css`. После копирования заменить селекторы:
- `[data-dir="a"][data-mode="dark"], [data-dir="a"] [data-mode="dark"]` → `[data-theme="aurora"][data-mode="dark"]`
- `[data-dir="a"][data-mode="light"], [data-dir="a"] [data-mode="light"]` → `[data-theme="aurora"][data-mode="light"]`
- Удалить блоки `[data-dir="b"]` и `[data-dir="c"]` (направления B и C не используем).
- Заменить корневой `.glass-root` → `[data-theme="aurora"]` (применяется к `<html>`).

- [ ] **Step 3: Create `app.css`**

Скопировать содержимое `design-reference/redesign/app.css` в `frontend/src/aurora/styles/app.css` без изменений (все классы — нейтральные, не зависят от data-атрибутов).

- [ ] **Step 4: Create `antdGlass.css`**

`frontend/src/aurora/styles/antdGlass.css`:
```css
/* Overlay на нативные AntD-компоненты в Aurora-режиме. */
/* Все правила обёрнуты в :where([data-theme="aurora"]) — нулевая специфичность для классики. */

:where([data-theme="aurora"]) .ant-form-item-label > label {
  color: var(--text-2);
  font-weight: 500;
  font-size: 13px;
}

:where([data-theme="aurora"]) .ant-input,
:where([data-theme="aurora"]) .ant-input-password,
:where([data-theme="aurora"]) .ant-input-number,
:where([data-theme="aurora"]) .ant-select-selector,
:where([data-theme="aurora"]) .ant-picker {
  background: var(--glass-bg) !important;
  border-color: var(--glass-border) !important;
  border-radius: var(--radius-sm) !important;
  color: var(--text) !important;
}

:where([data-theme="aurora"]) .ant-input:focus,
:where([data-theme="aurora"]) .ant-input-focused,
:where([data-theme="aurora"]) .ant-select-focused .ant-select-selector,
:where([data-theme="aurora"]) .ant-picker-focused {
  border-color: var(--accent-border) !important;
  box-shadow: 0 0 0 3px var(--accent-glow) !important;
}

:where([data-theme="aurora"]) .ant-btn {
  border-radius: var(--radius-pill);
  font-family: var(--font-body);
  font-weight: 600;
}

:where([data-theme="aurora"]) .ant-btn-primary {
  background: linear-gradient(110deg, var(--accent-1), var(--accent-2));
  border-color: transparent;
  box-shadow: 0 6px 22px var(--accent-glow), inset 0 1px 0 rgba(255,255,255,.35);
}

:where([data-theme="aurora"]) .ant-btn-default {
  background: var(--glass-bg);
  border-color: var(--glass-border);
  color: var(--text);
}

:where([data-theme="aurora"]) .ant-modal-content,
:where([data-theme="aurora"]) .ant-drawer-content {
  background: var(--glass-bg) !important;
  backdrop-filter: blur(var(--blur)) saturate(1.25);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
}

:where([data-theme="aurora"]) .ant-modal-header,
:where([data-theme="aurora"]) .ant-drawer-header {
  background: transparent !important;
  border-bottom-color: var(--glass-border);
}

:where([data-theme="aurora"]) .ant-table,
:where([data-theme="aurora"]) .ant-table-thead > tr > th,
:where([data-theme="aurora"]) .ant-table-tbody > tr > td {
  background: transparent !important;
  border-bottom-color: var(--glass-border) !important;
  color: var(--text);
}

:where([data-theme="aurora"]) .ant-table-thead > tr > th {
  color: var(--text-muted);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

:where([data-theme="aurora"]) .ant-table-tbody > tr:hover > td {
  background: var(--glass-bg) !important;
}

:where([data-theme="aurora"]) .ant-tabs-nav::before {
  border-bottom-color: var(--glass-border) !important;
}

:where([data-theme="aurora"]) .ant-tabs-tab-btn {
  color: var(--text-muted);
}

:where([data-theme="aurora"]) .ant-tabs-tab-active .ant-tabs-tab-btn {
  color: var(--accent-1) !important;
}

:where([data-theme="aurora"]) .ant-tabs-ink-bar {
  background: linear-gradient(90deg, var(--accent-1), var(--accent-2)) !important;
  box-shadow: 0 0 8px var(--accent-glow);
}

:where([data-theme="aurora"]) .ant-tag {
  background: var(--pill-bg);
  border-color: var(--pill-border);
  color: var(--text-2);
  border-radius: var(--radius-pill);
}

:where([data-theme="aurora"]) .ant-tree {
  background: transparent;
  color: var(--text);
}

:where([data-theme="aurora"]) .ant-tree-node-content-wrapper:hover {
  background: var(--glass-bg);
}

:where([data-theme="aurora"]) .ant-tree-node-selected {
  background: color-mix(in srgb, var(--accent-1) 12%, transparent) !important;
}

:where([data-theme="aurora"]) .ant-card {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius);
  backdrop-filter: blur(var(--blur)) saturate(1.25);
}

:where([data-theme="aurora"]) .ant-card-head {
  border-bottom-color: var(--glass-border);
  color: var(--text);
}

:where([data-theme="aurora"]) .ant-notification-notice {
  background: var(--glass-bg) !important;
  border: 1px solid var(--glass-border);
  backdrop-filter: blur(var(--blur));
}

:where([data-theme="aurora"]) .ant-dropdown-menu,
:where([data-theme="aurora"]) .ant-select-dropdown,
:where([data-theme="aurora"]) .ant-picker-dropdown {
  background: rgba(20, 25, 40, 0.95) !important;
  backdrop-filter: blur(var(--blur));
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

:where([data-theme="aurora"][data-mode="light"]) .ant-dropdown-menu,
:where([data-theme="aurora"][data-mode="light"]) .ant-select-dropdown,
:where([data-theme="aurora"][data-mode="light"]) .ant-picker-dropdown {
  background: rgba(255, 255, 255, 0.95) !important;
}

:where([data-theme="aurora"]) .ant-segmented {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
}

:where([data-theme="aurora"]) .ant-segmented-item-selected {
  background: linear-gradient(110deg, var(--accent-1), var(--accent-2)) !important;
  color: var(--on-accent);
}
```

- [ ] **Step 5: Create `aurora.css` entry point**

`frontend/src/aurora/styles/aurora.css`:
```css
@import './fonts.css';
@import './glass.css';
@import './app.css';
@import './antdGlass.css';
```

- [ ] **Step 6: Import in main.tsx**

`frontend/src/main.tsx` после `import './index.css';`:
```typescript
import './aurora/styles/aurora.css';
```

- [ ] **Step 7: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/aurora/styles/ frontend/src/main.tsx
git commit -m "feat(aurora): CSS-стили (glass tokens, app classes, antd overlay, fonts)"
```

---

### Task 5: ThemeProvider — выставлять data-theme / data-mode на html

**Files:**
- Modify: `frontend/src/contexts/ThemeContext.tsx`
- Test: `frontend/src/contexts/__tests__/ThemeContext.test.tsx` (новый)

- [ ] **Step 1: Write failing test**

`frontend/src/contexts/__tests__/ThemeContext.test.tsx`:
```typescript
import { describe, it, expect, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { ThemeProvider, useAppTheme } from '../ThemeContext';

function ThemeAttrs() {
  const { setTheme } = useAppTheme();
  return (
    <button data-testid="set-light" onClick={() => setTheme('aurora-light')} />
  );
}

describe('ThemeProvider DOM attributes', () => {
  beforeEach(() => {
    document.documentElement.removeAttribute('data-theme');
    document.documentElement.removeAttribute('data-mode');
  });

  it('sets data-theme=aurora data-mode=dark for aurora-dark', () => {
    render(<ThemeProvider><div /></ThemeProvider>);
    expect(document.documentElement.getAttribute('data-theme')).toBe('aurora');
    expect(document.documentElement.getAttribute('data-mode')).toBe('dark');
  });

  it('updates attributes when theme changes', () => {
    const { getByTestId } = render(<ThemeProvider><ThemeAttrs /></ThemeProvider>);
    act(() => { getByTestId('set-light').click(); });
    expect(document.documentElement.getAttribute('data-theme')).toBe('aurora');
    expect(document.documentElement.getAttribute('data-mode')).toBe('light');
  });

  it('classic themes set data-theme=classic without data-mode', () => {
    localStorage.setItem('app_theme', 'dark-blue');
    render(<ThemeProvider><div /></ThemeProvider>);
    expect(document.documentElement.getAttribute('data-theme')).toBe('classic');
    expect(document.documentElement.getAttribute('data-mode')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test — FAIL**

```bash
cd frontend && npm test -- ThemeContext.test.tsx
```

- [ ] **Step 3: Update ThemeProvider**

`frontend/src/contexts/ThemeContext.tsx` — заменить целиком:
```typescript
import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import type { AppTheme } from '../utils/constants';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
  isAurora: boolean;
  mode: 'dark' | 'light' | null;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'aurora-dark',
  setTheme: () => {},
  isAurora: true,
  mode: 'dark',
});

function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (
      v === 'dark-blue' || v === 'dark-slate' || v === 'dark-charcoal' || v === 'dark' ||
      v === 'aurora-dark' || v === 'aurora-light'
    ) return v;
  } catch {
    // localStorage unavailable
  }
  return 'aurora-dark';
}

function applyDomAttrs(t: AppTheme): void {
  const root = document.documentElement;
  if (t === 'aurora-dark') {
    root.setAttribute('data-theme', 'aurora');
    root.setAttribute('data-mode', 'dark');
  } else if (t === 'aurora-light') {
    root.setAttribute('data-theme', 'aurora');
    root.setAttribute('data-mode', 'light');
  } else {
    root.setAttribute('data-theme', 'classic');
    root.removeAttribute('data-mode');
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(readStoredTheme);

  useEffect(() => { applyDomAttrs(theme); }, [theme]);

  const setTheme = useCallback((t: AppTheme) => {
    try { localStorage.setItem('app_theme', t); } catch { /* ignore */ }
    setThemeState(t);
  }, []);

  const isAurora = theme === 'aurora-dark' || theme === 'aurora-light';
  const mode: 'dark' | 'light' | null = theme === 'aurora-dark' ? 'dark' : theme === 'aurora-light' ? 'light' : null;

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isAurora, mode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
```

- [ ] **Step 4: Run test — PASS**

```bash
cd frontend && npm test -- ThemeContext.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/contexts/ThemeContext.tsx frontend/src/contexts/__tests__/
git commit -m "feat(aurora): ThemeProvider выставляет data-theme/data-mode на <html>"
```

---

## Phase 2 — Aurora primitives

Все примитивы лежат в `frontend/src/aurora/primitives/`. Каждый — отдельный файл, отдельный коммит.

### Task 6: LucideIcon wrapper

**Files:**
- Create: `frontend/src/aurora/primitives/LucideIcon.tsx`

- [ ] **Step 1: Create the file**

```typescript
import { type LucideIcon as LucideIconType, type LucideProps } from 'lucide-react';

interface Props extends Omit<LucideProps, 'size'> {
  icon: LucideIconType;
  size?: number;
}

export function LucideIcon({ icon: Icon, size = 18, strokeWidth = 1.8, ...rest }: Props) {
  return <Icon size={size} strokeWidth={strokeWidth} {...rest} />;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/aurora/primitives/LucideIcon.tsx
git commit -m "feat(aurora): примитив LucideIcon"
```

---

### Task 7: GlassCard + GlassButton

**Files:**
- Create: `frontend/src/aurora/primitives/GlassCard.tsx`
- Create: `frontend/src/aurora/primitives/GlassButton.tsx`

- [ ] **Step 1: GlassCard**

```typescript
import { type ReactNode, type CSSProperties } from 'react';

interface Props {
  children: ReactNode;
  hover?: boolean;
  padding?: number | string;
  style?: CSSProperties;
  className?: string;
  onClick?: () => void;
  title?: ReactNode;
  extra?: ReactNode;
}

export function GlassCard({ children, hover, padding = 20, style, className = '', onClick, title, extra }: Props) {
  return (
    <div
      className={`glass ${hover ? 'glass-hover' : ''} ${className}`}
      style={{ padding: typeof padding === 'number' ? `${padding}px` : padding, ...style }}
      onClick={onClick}
    >
      {(title || extra) && (
        <div className="card-title" style={{ marginBottom: 14 }}>
          <span>{title}</span>
          {extra}
        </div>
      )}
      {children}
    </div>
  );
}
```

- [ ] **Step 2: GlassButton**

```typescript
import { type ReactNode, type CSSProperties, type MouseEvent } from 'react';

type Variant = 'primary' | 'ghost';

interface Props {
  children: ReactNode;
  variant?: Variant;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  block?: boolean;
  htmlType?: 'button' | 'submit' | 'reset';
  style?: CSSProperties;
  className?: string;
  title?: string;
}

export function GlassButton({
  children, variant = 'primary', onClick, disabled, loading, icon, block,
  htmlType = 'button', style, className = '', title,
}: Props) {
  const variantClass = variant === 'primary' ? 'gbtn-primary' : 'gbtn-ghost';
  return (
    <button
      type={htmlType}
      className={`gbtn ${variantClass} ${className}`}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      style={{ width: block ? '100%' : undefined, opacity: disabled ? 0.5 : 1, ...style }}
    >
      {loading ? <span className="num">…</span> : icon}
      {children}
    </button>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/aurora/primitives/GlassCard.tsx frontend/src/aurora/primitives/GlassButton.tsx
git commit -m "feat(aurora): примитивы GlassCard и GlassButton"
```

---

### Task 8: Pill + Badge

**Files:**
- Create: `frontend/src/aurora/primitives/Pill.tsx`
- Create: `frontend/src/aurora/primitives/Badge.tsx`

- [ ] **Step 1: Pill**

```typescript
import { type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
}

export function Pill({ children, icon, onClick }: Props) {
  return (
    <span className="pill" style={{ cursor: onClick ? 'pointer' : undefined }} onClick={onClick}>
      {icon}{children}
    </span>
  );
}
```

- [ ] **Step 2: Badge**

```typescript
import { type ReactNode } from 'react';

type Tone = 'good' | 'warn' | 'bad' | 'accent' | 'key';

interface Props {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}

export function Badge({ children, tone = 'accent', icon }: Props) {
  return (
    <span className={`badge badge-${tone}`}>
      {icon}{children}
    </span>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/aurora/primitives/Pill.tsx frontend/src/aurora/primitives/Badge.tsx
git commit -m "feat(aurora): примитивы Pill и Badge"
```

---

### Task 9: Track + GlowRing + NeonLine

**Files:**
- Create: `frontend/src/aurora/primitives/Track.tsx`
- Create: `frontend/src/aurora/primitives/GlowRing.tsx`
- Create: `frontend/src/aurora/primitives/NeonLine.tsx`

- [ ] **Step 1: Track**

```typescript
interface Props { pct: number; max?: number; glow?: boolean; color?: string }

export function Track({ pct, max = 130, glow = true, color }: Props) {
  const width = `${Math.min(pct, max) / max * 100}%`;
  return (
    <div className="track">
      <i style={{
        width,
        background: color || 'linear-gradient(90deg, var(--accent-1), var(--accent-2))',
        boxShadow: glow ? '0 0 10px var(--accent-glow)' : 'none',
      }} />
    </div>
  );
}
```

- [ ] **Step 2: GlowRing**

Скопировать функцию `GlowRing` из `design-reference/redesign/glass-ui.jsx` (строки 14-42), преобразовать в TS:

```typescript
interface Props {
  pct: number;
  sub?: string;
  uid?: string;
  size?: number;
  stroke?: number;
  color?: string;
}

export function GlowRing({ pct, sub, uid = 'r', size = 132, stroke = 11, color }: Props) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.min(pct, 100) / 100);
  const gid = `ring-${uid}`.replace(/[^a-z0-9]/gi, '');
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor={color || 'var(--accent-1)'} />
            <stop offset="1" stopColor={color || 'var(--accent-2)'} />
          </linearGradient>
          <filter id={`${gid}-g`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--track-bg)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${gid})`} strokeWidth={stroke}
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off} filter={`url(#${gid}-g)`} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <div className="num" style={{ fontSize: size * 0.23, fontWeight: 700 }}>{pct}<span style={{ fontSize: size * 0.12 }}>%</span></div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: NeonLine**

Скопировать из reference (строки 44-63), TS-вариант:

```typescript
interface Props { uid: string; points: number[]; height?: number }

export function NeonLine({ uid, points, height = 120 }: Props) {
  const w = 460, h = height, max = Math.max(...points), min = Math.min(...points), pad = 14;
  const xs = points.map((_, i) => pad + (i * (w - pad * 2)) / (points.length - 1));
  const ys = points.map((p) => h - pad - ((p - min) / (max - min || 1)) * (h - pad * 2));
  const line = xs.map((x, i) => `${i ? 'L' : 'M'}${x.toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');
  const area = `${line} L${xs[xs.length - 1].toFixed(1)} ${h} L${xs[0].toFixed(1)} ${h} Z`;
  const gid = `nl-${uid}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ width: '100%', height }}>
      <defs>
        <linearGradient id={`${gid}-s`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="var(--accent-1)" />
          <stop offset="1" stopColor="var(--accent-2)" />
        </linearGradient>
        <linearGradient id={`${gid}-a`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--accent-1)" stopOpacity="0.30" />
          <stop offset="1" stopColor="var(--accent-1)" stopOpacity="0" />
        </linearGradient>
        <filter id={`${gid}-g`} x="-20%" y="-50%" width="140%" height="200%">
          <feGaussianBlur stdDeviation="4" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      <path d={area} fill={`url(#${gid}-a)`} />
      <path d={line} fill="none" stroke={`url(#${gid}-s)`} strokeWidth="2.5" strokeLinecap="round" filter={`url(#${gid}-g)`} />
      <circle cx={xs[xs.length - 1]} cy={ys[ys.length - 1]} r="4" fill="var(--accent-2)" filter={`url(#${gid}-g)`} />
    </svg>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/aurora/primitives/Track.tsx frontend/src/aurora/primitives/GlowRing.tsx frontend/src/aurora/primitives/NeonLine.tsx
git commit -m "feat(aurora): примитивы Track, GlowRing, NeonLine"
```

---

### Task 10: GlassTabs + Segmented + GlassInput + Avatar

**Files:**
- Create: `frontend/src/aurora/primitives/GlassTabs.tsx`
- Create: `frontend/src/aurora/primitives/Segmented.tsx`
- Create: `frontend/src/aurora/primitives/GlassInput.tsx`
- Create: `frontend/src/aurora/primitives/Avatar.tsx`

- [ ] **Step 1: GlassTabs**

```typescript
import { type ReactNode } from 'react';

interface Tab { key: string; label: ReactNode; icon?: ReactNode }

interface Props {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
}

export function GlassTabs({ tabs, active, onChange }: Props) {
  return (
    <div className="gtabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`gtab ${active === t.key ? 'active' : ''}`}
          onClick={() => onChange(t.key)}
        >
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Segmented**

```typescript
import { type ReactNode } from 'react';

interface Option { value: string; label: ReactNode }

interface Props {
  options: Option[];
  value: string;
  onChange: (v: string) => void;
}

export function Segmented({ options, value, onChange }: Props) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button
          key={o.value}
          className={value === o.value ? 'active' : ''}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: GlassInput**

```typescript
import { type ReactNode, type InputHTMLAttributes } from 'react';

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  trailing?: ReactNode;
}

export function GlassInput({ icon, trailing, style, ...rest }: Props) {
  return (
    <div className="ginput" style={style}>
      {icon}
      <input {...rest} />
      {trailing}
    </div>
  );
}
```

- [ ] **Step 4: Avatar**

```typescript
interface Props { name: string; color?: string; size?: number }

export function Avatar({ name, color = 'var(--accent-1)', size = 28 }: Props) {
  const ini = name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2);
  return (
    <span style={{
      width: size, height: size, borderRadius: '50%', flexShrink: 0,
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.4, fontWeight: 700, color: 'var(--on-accent)',
      background: `linear-gradient(135deg, ${color}, var(--accent-2))`,
      boxShadow: '0 0 0 1px var(--glass-border)',
    }}>{ini}</span>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/aurora/primitives/
git commit -m "feat(aurora): примитивы GlassTabs, Segmented, GlassInput, Avatar"
```

---

### Task 11: Barrel экспорт

**Files:**
- Create: `frontend/src/aurora/primitives/index.ts`
- Create: `frontend/src/aurora/index.ts`

- [ ] **Step 1: Primitives barrel**

`frontend/src/aurora/primitives/index.ts`:
```typescript
export { LucideIcon } from './LucideIcon';
export { GlassCard } from './GlassCard';
export { GlassButton } from './GlassButton';
export { Pill } from './Pill';
export { Badge } from './Badge';
export { Track } from './Track';
export { GlowRing } from './GlowRing';
export { NeonLine } from './NeonLine';
export { GlassTabs } from './GlassTabs';
export { Segmented } from './Segmented';
export { GlassInput } from './GlassInput';
export { Avatar } from './Avatar';
```

- [ ] **Step 2: Root barrel**

`frontend/src/aurora/index.ts`:
```typescript
export * from './primitives';
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/aurora/primitives/index.ts frontend/src/aurora/index.ts
git commit -m "feat(aurora): barrel-экспорты примитивов"
```

---

## Phase 3 — Aurora shell

### Task 12: AuroraSidebar

**Files:**
- Create: `frontend/src/aurora/shell/AuroraSidebar.tsx`

Используем те же группы и роуты, что в [`SideMenu.tsx`](frontend/src/components/Layout/SideMenu.tsx) — `overview` / `planning` / `data`. Иконки берём из `lucide-react` (LayoutDashboard, FolderKanban, BarChart3, Lightbulb, Rocket, Users, ListChecks, Presentation, RefreshCw, Tags, MessageCircle, Settings).

- [ ] **Step 1: Создать AuroraSidebar.tsx**

```typescript
import { useNavigate, useLocation } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard, FolderKanban, BarChart3, Lightbulb, Rocket,
  Users, ListChecks, Presentation, Network,
  RefreshCw, Tags, MessageCircle, Settings,
  type LucideIcon as LucideIconType,
} from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { getHiddenSections } from '../../api/uiConfig';

interface NavItem { key: string; icon: LucideIconType; label: string }
interface NavGroup { label: string; items: NavItem[] }

export function AuroraSidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const { data: hidden } = useQuery({
    queryKey: ['ui-config', 'hidden-sections'],
    queryFn: getHiddenSections,
    staleTime: 60_000,
    enabled: !!user,
  });
  const hiddenSet = new Set(hidden?.keys ?? []);
  const isHidden = (k: string) => hiddenSet.has(k);

  const groups: NavGroup[] = [
    { label: 'Обзор', items: [
      { key: '/', icon: LayoutDashboard, label: 'Дашборд' },
      { key: '/projects', icon: FolderKanban, label: 'Проекты' },
      { key: '/analytics', icon: BarChart3, label: 'Аналитика' },
      { key: '/analytics/work-type-report', icon: Lightbulb, label: 'Тематический отчёт' },
      { key: '/executive', icon: Rocket, label: 'Сводка для руководителя' },
    ].filter((it) => !isHidden(it.key)) },
    { label: 'Планирование', items: [
      { key: '/capacity', icon: Users, label: 'Ресурсы' },
      { key: '/backlog', icon: ListChecks, label: 'Целевые задачи' },
      { key: '/planning', icon: Presentation, label: 'Сценарии' },
      { key: '/resource-planning', icon: Network, label: 'Ресурс. планир.' },
    ].filter((it) => !isHidden(it.key)) },
    { label: 'Данные', items: [
      { key: '/sync', icon: RefreshCw, label: 'Синхронизация' },
      { key: '/categories', icon: Tags, label: 'Категории задач' },
      { key: '/feedback', icon: MessageCircle, label: 'Обратная связь' },
      ...(isAdmin ? [{ key: '/settings', icon: Settings, label: 'Настройки' }] : []),
    ].filter((it) => !isHidden(it.key)) },
  ].filter((g) => g.items.length > 0);

  const selectedKey = location.pathname.startsWith('/projects') ? '/projects' : location.pathname;

  return (
    <div className="glass side">
      <div className="side-logo">
        <svg width="30" height="30" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="13" stroke="var(--accent-1)" strokeWidth="1.5" opacity="0.4" />
          <path d="M5 16a11 11 0 0 1 22 0" stroke="var(--accent-1)" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="16" cy="5" r="2.6" fill="var(--accent-1)" />
          <circle cx="16" cy="16" r="2.2" fill="var(--accent-2)" />
        </svg>
        <div style={{ lineHeight: 1.1 }}>
          <div className="serif" style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em' }}>Jira</div>
          <div style={{ fontSize: 9.5, textTransform: 'uppercase', letterSpacing: '0.18em', color: 'var(--accent-1)', fontWeight: 600, marginTop: 1 }}>Analytics</div>
        </div>
      </div>
      <div className="scroll-y" style={{ flex: 1, margin: '0 -4px', padding: '0 4px' }}>
        {groups.map((g) => (
          <div key={g.label}>
            <div className="side-group">{g.label}</div>
            {g.items.map(({ key, icon: Icon, label }) => (
              <button
                key={key}
                className={`side-item${selectedKey === key ? ' active' : ''}`}
                onClick={() => navigate(key)}
              >
                <span className="side-ico"><Icon size={17} strokeWidth={1.8} /></span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/aurora/shell/AuroraSidebar.tsx
git commit -m "feat(aurora): AuroraSidebar — Lucide-иконки, glass-стили, та же навигация"
```

---

### Task 13: AuroraTopbar + ThemeToggle

**Files:**
- Create: `frontend/src/aurora/shell/ThemeToggle.tsx`
- Create: `frontend/src/aurora/shell/AuroraTopbar.tsx`

- [ ] **Step 1: ThemeToggle**

`frontend/src/aurora/shell/ThemeToggle.tsx`:
```typescript
import { Sun, Moon, Palette } from 'lucide-react';
import { useAppTheme } from '../../contexts/ThemeContext';
import { useSaveTheme } from '../../hooks/useTheme';
import type { AppTheme } from '../../utils/constants';

const CYCLE: AppTheme[] = ['aurora-dark', 'aurora-light', 'dark-blue'];

export function ThemeToggle() {
  const { theme, isAurora, mode } = useAppTheme();
  const saveTheme = useSaveTheme();

  const next = (): AppTheme => {
    const idx = CYCLE.indexOf(theme);
    return CYCLE[(idx + 1) % CYCLE.length] ?? 'aurora-dark';
  };

  const title = isAurora
    ? (mode === 'dark' ? 'Aurora светлая →' : 'Классика →')
    : 'Aurora тёмная →';

  const Icon = isAurora ? (mode === 'dark' ? Sun : Palette) : Moon;

  return (
    <button
      className="icon-btn"
      title={title}
      onClick={() => saveTheme(next())}
    >
      <Icon size={17} strokeWidth={1.8} />
    </button>
  );
}
```

- [ ] **Step 2: AuroraTopbar**

`frontend/src/aurora/shell/AuroraTopbar.tsx`:
```typescript
import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { trackAction } from '../../lib/usage/track';
import GlobalTeamFilterButton from '../../components/Layout/GlobalTeamFilterButton';
import GlobalPeriodPicker from '../../components/shared/GlobalPeriodPicker';
import GlobalHelpButton from '../../components/Layout/GlobalHelpButton';
import SyncIndicator from '../../components/Layout/SyncIndicator';
import { Avatar } from '../primitives/Avatar';
import { ThemeToggle } from './ThemeToggle';

export function AuroraTopbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <div className="topbar">
      <div className="eyebrow">Анализ Jira · Планирование квартала</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <SyncIndicator />
        {user && (
          <>
            <GlobalTeamFilterButton />
            <GlobalPeriodPicker />
            <GlobalHelpButton />
            <ThemeToggle />
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Avatar name={user.display_name} size={30} />
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{user.display_name}</span>
            </span>
            <button className="icon-btn" title="Выйти" onClick={handleLogout}>
              <LogOut size={17} strokeWidth={1.8} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
```

Примечание: компоненты `GlobalTeamFilterButton`, `GlobalPeriodPicker`, `GlobalHelpButton`, `SyncIndicator` остаются нативными — они будут перетемизированы через `antdGlass.css` (если используют AntD) или их собственные стили (если кастомные).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/aurora/shell/
git commit -m "feat(aurora): AuroraTopbar с ThemeToggle (3-circle cycle dark→light→classic)"
```

---

### Task 14: AuroraPageHead

**Files:**
- Create: `frontend/src/aurora/shell/AuroraPageHead.tsx`

- [ ] **Step 1: Create**

```typescript
import { type ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
}

export function AuroraPageHead({ title, subtitle, extra }: Props) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, marginBottom: 20 }}>
      <div>
        {subtitle && <div className="eyebrow" style={{ marginBottom: 5 }}>{subtitle}</div>}
        <div className="serif" style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-0.02em' }}>{title}</div>
      </div>
      {extra}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/aurora/shell/AuroraPageHead.tsx
git commit -m "feat(aurora): AuroraPageHead — eyebrow + Fraunces заголовок + extra slot"
```

---

### Task 15: AuroraShell + интеграция в AppLayout

**Files:**
- Create: `frontend/src/aurora/shell/AuroraShell.tsx`
- Modify: `frontend/src/components/Layout/AppLayout.tsx`

- [ ] **Step 1: Create AuroraShell**

```typescript
import { type ReactNode } from 'react';
import { Outlet } from 'react-router';
import { useAuth } from '../../hooks/useAuth';
import { AuroraSidebar } from './AuroraSidebar';
import { AuroraTopbar } from './AuroraTopbar';
import FeedbackButton from '../../components/feedback/FeedbackButton';
import WhatsNewGate from '../../components/release-notes/WhatsNewGate';
import { HelpProvider } from '../../contexts/HelpContext';
import { usePageView } from '../../lib/usage/usePageView';
import { useHeartbeat } from '../../lib/usage/useHeartbeat';
import { useEventStream } from '../../hooks/useEventStream';
import { useThemeSync } from '../../hooks/useTheme';

function UsageTracker(): ReactNode {
  usePageView();
  useHeartbeat();
  return null;
}

export function AuroraShell() {
  const { user } = useAuth();
  useEventStream();
  useThemeSync();

  return (
    <HelpProvider>
      <div style={{ display: 'flex', gap: 16, height: '100vh', padding: 16, boxSizing: 'border-box' }}>
        <AuroraSidebar />
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <AuroraTopbar />
          <div className="scroll-y" style={{ flex: 1, paddingRight: 4 }}>
            <Outlet />
          </div>
        </div>
      </div>
      <FeedbackButton />
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
    </HelpProvider>
  );
}
```

- [ ] **Step 2: Modify AppLayout — dispatch shell на основании isAurora**

Заменить `frontend/src/components/Layout/AppLayout.tsx` целиком:
```typescript
import { useAppTheme } from '../../contexts/ThemeContext';
import { AuroraShell } from '../../aurora/shell/AuroraShell';
import ClassicShell from './ClassicShell';

export default function AppLayout() {
  const { isAurora } = useAppTheme();
  return isAurora ? <AuroraShell /> : <ClassicShell />;
}
```

- [ ] **Step 3: Переименовать старый AppLayout в ClassicShell**

```bash
git mv frontend/src/components/Layout/AppLayout.tsx frontend/src/components/Layout/ClassicShell.tsx
```

Затем восстановить `AppLayout.tsx` со Step 2 (поскольку `git mv` оставил пустой `AppLayout.tsx`).

Внутри нового `ClassicShell.tsx`:
1. Переименовать `export default function AppLayout()` → `export default function ClassicShell()`.
2. Оставить функционал как был — это рабочая классика.

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 5: Manual smoke test**

Запустить dev (`cd frontend && npm run dev`), открыть `http://localhost:5173`. Залогиниться. Через `localStorage.setItem('app_theme', 'aurora-dark'); location.reload()` проверить что:
- сайдбар = AuroraSidebar (glass), Lucide-иконки
- топбар = AuroraTopbar
- ThemeToggle цикл работает (aurora-dark → aurora-light → dark-blue → aurora-dark)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/aurora/shell/AuroraShell.tsx frontend/src/components/Layout/AppLayout.tsx frontend/src/components/Layout/ClassicShell.tsx
git commit -m "feat(aurora): AuroraShell + диспетчер шелла в AppLayout (classic/aurora)"
```

---

## Phase 4 — AntD ConfigProvider tokens для Aurora

### Task 16: auroraAntdTokens + переключатель в main.tsx

**Files:**
- Create: `frontend/src/aurora/theme/auroraAntdTokens.ts`
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Create auroraAntdTokens**

```typescript
import { theme as antdTheme } from 'antd';
import type { ThemeConfig } from 'antd';

export function buildAuroraAntdConfig(mode: 'dark' | 'light'): ThemeConfig {
  const isDark = mode === 'dark';
  return {
    algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: isDark ? '#38bdf8' : '#0ea5e9',
      colorBgContainer: 'transparent',
      colorBgElevated: isDark ? 'rgba(20,25,40,0.95)' : 'rgba(255,255,255,0.95)',
      colorBgLayout: 'transparent',
      colorBorderSecondary: isDark ? 'rgba(255,255,255,0.10)' : 'rgba(60,90,160,0.12)',
      colorText: isDark ? '#eaf0fb' : '#16203a',
      colorTextSecondary: isDark ? '#b8c6e0' : '#3f4d6e',
      colorTextTertiary: isDark ? '#7f90b0' : '#707f9e',
      colorTextQuaternary: isDark ? '#5a6a85' : '#8b97b3',
      borderRadius: 12,
      borderRadiusLG: 20,
      colorLink: isDark ? '#a78bfa' : '#7c5cf6',
      fontFamily: "'Manrope', -apple-system, 'Segoe UI', sans-serif",
      fontFamilyCode: "'JetBrains Mono', ui-monospace, monospace",
      fontSize: 14,
    },
    components: {
      Layout: {
        siderBg: 'transparent',
        headerBg: 'transparent',
        bodyBg: 'transparent',
      },
      Menu: {
        darkItemBg: 'transparent',
        darkItemSelectedBg: 'transparent',
        itemBg: 'transparent',
      },
      Card: {
        colorBgContainer: 'transparent',
      },
      Table: {
        colorBgContainer: 'transparent',
        headerBg: 'transparent',
      },
      Modal: {
        contentBg: 'transparent',
        headerBg: 'transparent',
      },
      Tabs: {
        inkBarColor: isDark ? '#38bdf8' : '#0ea5e9',
        itemActiveColor: isDark ? '#38bdf8' : '#0ea5e9',
        itemSelectedColor: isDark ? '#38bdf8' : '#0ea5e9',
      },
    },
  };
}
```

- [ ] **Step 2: Modify main.tsx — выбор конфига по теме**

Открыть `frontend/src/main.tsx`. После импортов добавить:
```typescript
import { buildAuroraAntdConfig } from './aurora/theme/auroraAntdTokens';
```

Заменить функцию `ThemedApp`:
```typescript
function ThemedApp() {
  const { theme: themeName, isAurora, mode } = useAppTheme();
  const t = APP_THEMES[themeName].tokens;

  const config = isAurora && mode
    ? buildAuroraAntdConfig(mode)
    : {
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: t.primary,
          colorBgContainer: t.cardBg,
          colorBgElevated: t.cardBg,
          colorBgLayout: t.pageBg,
          colorBorderSecondary: t.border,
          colorText: t.textPrimary,
          colorTextSecondary: t.textSecondary,
          colorTextTertiary: t.textMuted,
          colorTextQuaternary: t.textHint,
          borderRadius: 8,
          colorLink: t.primarySecondary,
          fontFamily: FONTS.body,
          fontFamilyCode: FONTS.mono,
          fontSize: 14,
        },
        components: {
          Layout: { siderBg: t.sidebarBg, headerBg: t.sidebarBg, bodyBg: t.pageBg },
          Menu: { darkItemBg: t.sidebarBg, darkItemSelectedBg: t.darkAccent, darkItemColor: t.textMuted, darkItemSelectedColor: t.primary, darkItemHoverColor: t.primarySecondary },
          Card: { colorBgContainer: t.cardBg, colorBorderSecondary: t.border },
          Table: { colorBgContainer: t.cardBg, headerBg: t.darkAccent, rowHoverBg: t.darkRows, borderColor: t.border },
          Modal: { contentBg: t.cardBg, headerBg: t.cardBg },
          Statistic: { colorTextDescription: t.textMuted, contentFontSize: 32 },
          Typography: { fontWeightStrong: 700 },
          Tabs: { inkBarColor: t.primary, itemActiveColor: t.primary, itemSelectedColor: t.primary },
          Collapse: { headerBg: t.darkAccent, contentBg: t.cardBg },
        },
      };

  return (
    <ConfigProvider locale={ruRU} theme={config}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  );
}
```

- [ ] **Step 3: Verify build**

```bash
cd frontend && npm run build
```
Expected: PASS.

- [ ] **Step 4: Smoke**

`npm run dev` → переключить тему через ThemeToggle. Проверить что AntD-компоненты (Modal, Drawer, Select dropdown) подхватывают Aurora-стиль.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/aurora/theme/ frontend/src/main.tsx
git commit -m "feat(aurora): ConfigProvider токены для aurora-dark/light"
```

---

## Phase 5 — Recharts Aurora palette

### Task 17: CHART_COLORS_AURORA + glass Tooltip

**Files:**
- Create: `frontend/src/aurora/charts/colors.ts`
- Create: `frontend/src/aurora/charts/GlassTooltip.tsx`
- Create: `frontend/src/aurora/charts/useChartTheme.ts`

- [ ] **Step 1: colors.ts**

```typescript
export const CHART_COLORS_AURORA = {
  blue: '#38bdf8',
  violet: '#a78bfa',
  green: '#34d399',
  yellow: '#fbbf24',
  red: '#fb7185',
  cyan: '#22d3ee',
  pink: '#e879f9',
  amber: '#fcd34d',
  teal: '#2dd4bf',
  neutral: '#7f90b0',
} as const;

export const CHART_PALETTE_AURORA = [
  CHART_COLORS_AURORA.blue,
  CHART_COLORS_AURORA.violet,
  CHART_COLORS_AURORA.green,
  CHART_COLORS_AURORA.yellow,
  CHART_COLORS_AURORA.red,
  CHART_COLORS_AURORA.cyan,
  CHART_COLORS_AURORA.pink,
  CHART_COLORS_AURORA.amber,
  CHART_COLORS_AURORA.teal,
  CHART_COLORS_AURORA.neutral,
];
```

- [ ] **Step 2: GlassTooltip**

```typescript
import { type ReactNode } from 'react';

interface Props {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: ReactNode;
}

export function GlassTooltip({ active, payload, label }: Props) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="glass" style={{ padding: '10px 14px', minWidth: 140 }}>
      {label && <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>}
      {payload.map((p) => (
        <div key={p.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: p.color }} />
            {p.name}
          </span>
          <span className="num" style={{ fontWeight: 600 }}>{p.value}</span>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: useChartTheme**

```typescript
import { useMemo } from 'react';
import { useAppTheme } from '../../contexts/ThemeContext';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import { CHART_COLORS_AURORA, CHART_PALETTE_AURORA } from './colors';

export function useChartTheme() {
  const { isAurora } = useAppTheme();
  return useMemo(() => ({
    isAurora,
    palette: isAurora ? CHART_PALETTE_AURORA : Object.values(CHART_COLORS),
    colors: isAurora ? CHART_COLORS_AURORA : CHART_COLORS,
    gridStroke: isAurora ? 'rgba(255,255,255,0.10)' : DARK_THEME.border,
    axisColor: isAurora ? '#7f90b0' : DARK_THEME.textMuted,
    tooltipBg: isAurora ? 'rgba(20,25,40,0.95)' : DARK_THEME.cardBg,
  }), [isAurora]);
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/aurora/charts/
git commit -m "feat(aurora): палитра Recharts + GlassTooltip + useChartTheme хук"
```

---

## Phase 6 — Reskin лёгких страниц

Для **каждой** страницы в этой фазе принцип одинаковый:
1. Импортировать примитивы из `frontend/src/aurora/`.
2. Условно рендерить Aurora-вариант блоков через `useAppTheme().isAurora`.
3. Заменить `Card` → `GlassCard`, `Button` → `GlassButton`, `Tag` → `Pill/Badge`, `Tabs` → `GlassTabs`, `Segmented` (AntD) → собственный `Segmented`.
4. Кнопку «PageHeader title» заменить на `AuroraPageHead`.
5. Внутри форм AntD остаётся как есть — overlay `antdGlass.css` уже всё перекрашивает.

Каждая задача = одна страница = один коммит.

### Task 18: /login — Aurora-вариант

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Обернуть форму в glass-карточку, добавить Aurora-фон**

Заменить компонент `LoginPage` целиком:
```typescript
import { Form, Input } from 'antd';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { HelpCircle } from 'lucide-react';
import { getMe, login as apiLogin } from '../api/auth';
import { useAuth } from '../hooks/useAuth';
import { trackAction } from '../lib/usage/track';
import HelpDrawer from '../components/shared/HelpDrawer';
import loginHelp from '../../../docs/help/login.md?raw';
import { useAppTheme } from '../contexts/ThemeContext';
import { GlassCard } from '../aurora/primitives/GlassCard';
import { GlassButton } from '../aurora/primitives/GlassButton';

interface LoginForm { email: string; password: string }

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const { isAurora } = useAppTheme();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);

  async function onFinish(values: LoginForm) {
    setLoading(true);
    setError(null);
    try {
      await apiLogin(values.email, values.password);
      const profile = await getMe();
      login(profile);
      trackAction('login');
      const redirect = profile.role === 'manager' && profile.default_team
        ? `/?teams=${encodeURIComponent(profile.default_team)}`
        : '/';
      navigate(redirect, { replace: true });
    } catch {
      setError('Неверный email или пароль');
    } finally {
      setLoading(false);
    }
  }

  const form = (
    <Form layout="vertical" onFinish={onFinish} requiredMark={false}>
      <Form.Item name="email" label="Email" rules={[{ required: true, message: 'Введите email' }]}>
        <Input type="email" size="large" />
      </Form.Item>
      <Form.Item name="password" label="Пароль" rules={[{ required: true, message: 'Введите пароль' }]}>
        <Input.Password size="large" />
      </Form.Item>
      {error && (
        <div style={{ color: isAurora ? 'var(--bad)' : '#ff4d4f', marginBottom: 16, textAlign: 'center' }}>
          {error}
        </div>
      )}
      {isAurora ? (
        <GlassButton htmlType="submit" loading={loading} block>Войти</GlassButton>
      ) : (
        <Form.Item>
          {/* Classic submit */}
          <button type="submit" disabled={loading} style={{
            width: '100%', height: 40, background: '#1677ff', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer',
          }}>Войти</button>
        </Form.Item>
      )}
    </Form>
  );

  if (isAurora) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
        <GlassCard style={{ width: 380 }}>
          <div className="serif" style={{ fontSize: 26, fontWeight: 600, textAlign: 'center', marginBottom: 6 }}>Jira Analytics</div>
          <div className="eyebrow" style={{ textAlign: 'center', marginBottom: 24 }}>Вход в сервис</div>
          {form}
          <div style={{ textAlign: 'center', marginTop: 12 }}>
            <button className="gbtn gbtn-ghost" style={{ height: 32, padding: '0 12px' }} onClick={() => setHelpOpen(true)}>
              <HelpCircle size={14} /> Справка
            </button>
          </div>
        </GlassCard>
        <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} title="Вход в сервис" content={loginHelp} imageBase="/help-assets/" />
      </div>
    );
  }

  // Classic fallback — original layout
  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#141414' }}>
      <div style={{ width: 360 }}>
        <h3 style={{ textAlign: 'center', marginBottom: 32, color: '#fff' }}>Jira Analytics</h3>
        {form}
        <HelpDrawer open={helpOpen} onClose={() => setHelpOpen(false)} title="Вход в сервис" content={loginHelp} imageBase="/help-assets/" />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Manual test**

`npm run dev`, открыть `/login` в обоих режимах. Проверить:
- Aurora: glass-карточка по центру, эмбер-фон от градиентов, кнопка glow
- Классика: чёрный фон, как было

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(aurora): /login — glass-карточка по центру, gradient бэкграунд"
```

---

### Task 19: /settings (11 вкладок)

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

**Подход:** AntD `Tabs` остаются (overlay перекрасит), но обёртка страницы — `GlassCard`. Каждая вкладка-компонент уже использует свои Card/Form — overlay их перекрасит автоматически.

- [ ] **Step 1: Read current SettingsPage**

```bash
```

Просмотреть структуру файла. Найти `<PageHeader title="Настройки" ... />` и `<Tabs ... />`.

- [ ] **Step 2: Подменить PageHeader на AuroraPageHead в Aurora-режиме**

В начале компонента:
```typescript
import { useAppTheme } from '../contexts/ThemeContext';
import { AuroraPageHead } from '../aurora/shell/AuroraPageHead';
import { GlassCard } from '../aurora/primitives/GlassCard';
```

В JSX, перед `<Tabs>`:
```typescript
const { isAurora } = useAppTheme();
// ...
{isAurora ? (
  <AuroraPageHead title="Настройки" subtitle="Конфигурация сервиса" />
) : (
  <PageHeader title="Настройки" />
)}
<GlassCard padding={0} style={{ padding: isAurora ? 20 : 16 }}>
  <Tabs ... />
</GlassCard>
```

В классике `GlassCard` всё равно сработает (тогда `data-theme=classic` → `.glass` рендерится прозрачно).

- [ ] **Step 3: Smoke**

`npm run dev`, `/settings`, все 11 вкладок проверить в Aurora-режиме. Формы (Connection, ScopeAdmin, JiraFields, etc) должны выглядеть в стекле.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx
git commit -m "feat(aurora): /settings — AuroraPageHead + GlassCard обёртка вкладок"
```

---

### Task 20: /sync (3 вкладки + PipelineRunner)

**Files:**
- Modify: `frontend/src/pages/SyncHubPage.tsx`
- Modify: `frontend/src/components/sync/PipelineRunner.tsx`

- [ ] **Step 1: SyncHubPage wrapper**

Аналогично Task 19 — `AuroraPageHead` + `GlassCard` вокруг `Tabs`.

- [ ] **Step 2: PipelineRunner — режим-кнопки в glass-стиле**

В `PipelineRunner` найти 3 кнопки режимов (быстрый/обычный/полный). В Aurora-режиме: каждая кнопка — `GlassCard hover` с иконкой Lucide + описанием + кнопкой запуска (`GlassButton primary`).

Прогресс-бар синхронизации → `Track` (neon из примитивов).

- [ ] **Step 3: SyncHistory — лента запусков**

В Aurora-режиме каждый запуск в ленте — `GlassCard` с pill-статусом (success → `Badge tone="good"`, fail → `tone="bad"`).

- [ ] **Step 4: Smoke**

Запустить тестовый sync, проверить что лента и progress-bar выглядят корректно.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SyncHubPage.tsx frontend/src/components/sync/
git commit -m "feat(aurora): /sync — glass карточки режимов, neon-track прогресса, pill-статусы"
```

---

### Task 21: /feedback (список + drawer + форма)

**Files:**
- Modify: `frontend/src/pages/FeedbackPage.tsx`
- Modify: `frontend/src/components/feedback/FeedbackList.tsx`
- Modify: `frontend/src/components/feedback/FeedbackDetailDrawer.tsx`

- [ ] **Step 1: AuroraPageHead + GlassCard**

В `FeedbackPage` обернуть содержимое в `GlassCard`, заголовок → `AuroraPageHead`.

- [ ] **Step 2: FeedbackList**

Каждый элемент списка в Aurora-режиме — `GlassCard glass-hover` с pill-категорией. AntD `Form` (если есть форма создания) — оставить нативной, overlay перекрасит.

- [ ] **Step 3: Drawer**

AntD `Drawer` — overlay уже даст glass-эффект. Внутри: replace `Tag` → `Badge`, `Card` → `GlassCard`.

- [ ] **Step 4: Smoke + commit**

```bash
git add frontend/src/pages/FeedbackPage.tsx frontend/src/components/feedback/
git commit -m "feat(aurora): /feedback — glass карточки списка, pill-категории"
```

---

### Task 22: /capacity (фильтры + heatmap + drawer сотрудника)

**Files:**
- Modify: `frontend/src/pages/CapacityPage.tsx`
- Modify: `frontend/src/components/capacity/AbsenceHeatmap.tsx`
- Modify: `frontend/src/components/capacity/RolesTab.tsx`

- [ ] **Step 1: PageHead + фильтры**

`AuroraPageHead` сверху. Переключатель quarter/year/month — `Segmented` примитив (вместо AntD `Segmented`).

- [ ] **Step 2: Heatmap**

`AbsenceHeatmap` — это таблица. В Aurora-режиме применить классы `.gtable` поверх, заменить cell-классы на `.heat-over/.heat-warn/.heat-ok/.heat-good`. Overload >110% — `--bad` фон.

- [ ] **Step 3: EmployeeDrawer**

AntD `Drawer` — overlay даст glass. Внутри: `Card` → `GlassCard`, `Tag` → `Badge`. Аватар сотрудника → `Avatar` primitive.

- [ ] **Step 4: Smoke + commit**

```bash
git add frontend/src/pages/CapacityPage.tsx frontend/src/components/capacity/
git commit -m "feat(aurora): /capacity — glass фильтры + heatmap с тинтами + Avatar primitive"
```

---

### Task 23: /backlog (3 вкладки + карточки инициатив)

**Files:**
- Modify: `frontend/src/pages/BacklogPage.tsx`
- Modify: `frontend/src/components/backlog/BacklogManualModal.tsx`

- [ ] **Step 1: AuroraPageHead + GlassTabs**

Заменить AntD `Tabs` на `GlassTabs` primitive (controlled, по ключам `active/in-work/archive`).

- [ ] **Step 2: Initiative cards**

Каждая инициатива — `GlassCard glass-hover`. Pill «команда» / «приоритет» / «квартал» (если есть). Кнопки массовых операций — `GlassButton ghost`.

- [ ] **Step 3: BacklogManualModal**

AntD `Modal` — overlay перекрасит. Внутренние `Form` — нативные.

- [ ] **Step 4: Smoke + commit**

```bash
git add frontend/src/pages/BacklogPage.tsx frontend/src/components/backlog/
git commit -m "feat(aurora): /backlog — GlassTabs + glass карточки инициатив с pills"
```

---

### Task 24: /planning (сценарий + матрица покрытия)

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`
- Modify: `frontend/src/components/planning/RoleCapacityBar.tsx`
- Modify: `frontend/src/components/planning/ApproveCelebration.tsx`

- [ ] **Step 1: AuroraPageHead + GlassCard для сценария**

- [ ] **Step 2: RoleCapacityBar → Track**

Заменить SVG/div bars на `Track pct={...} max={130} glow />`. Перецвет под нагрузку >110% — добавить prop `color={'var(--bad)'}`.

- [ ] **Step 3: ApproveCelebration**

AntD `Modal` overlay + внутри — glass-фон, акценты Aurora.

- [ ] **Step 4: PlanningCapacityPanel**

Карточки ролей — `GlassCard`.

- [ ] **Step 5: Smoke + commit**

```bash
git add frontend/src/pages/PlanningPage.tsx frontend/src/components/planning/
git commit -m "feat(aurora): /planning — Track-бары нагрузки, glass карточки ролей"
```

---

### Task 25: /projects (master-detail + presentation)

**Files:**
- Modify: `frontend/src/pages/ProjectsPage.tsx`
- Modify: `frontend/src/components/projects/ProjectListCard.tsx`
- Modify: `frontend/src/components/projects/ProjectDetailPanel.tsx`
- Modify: `frontend/src/components/projects/ProjectAnalysisView.tsx`
- Modify: `frontend/src/components/projects/ProjectPresentationView.tsx`
- Modify: `frontend/src/components/projects/cards/*` (7 файлов)
- Modify: `frontend/src/components/projects/presentation/ProjectHero.tsx`

- [ ] **Step 1: List**

`ProjectListCard` → `GlassCard glass-hover`. Pill категорий.

- [ ] **Step 2: Detail panel — 7 секций**

Каждая `ProjectXxxCard` уже AntD `Card` — обернуть в `GlassCard`. `StarRating`, `DonutChart` — перекрасить под Aurora-палитру (через `useChartTheme`).

- [ ] **Step 3: Presentation view**

`ProjectHero` — Fraunces заголовок, NeonLine спарклайн прогресса. `ProjectStorySection` — glass-блоки.

- [ ] **Step 4: Smoke + commit**

```bash
git add frontend/src/pages/ProjectsPage.tsx frontend/src/components/projects/
git commit -m "feat(aurora): /projects master-detail + presentation в стекле, DonutChart Aurora palette"
```

---

## Phase 7 — Reskin тяжёлых страниц

### Task 26: / Dashboard (4 виджета + графики)

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`
- Modify: `frontend/src/components/dashboard/*` (виджеты)

- [ ] **Step 1: AuroraPageHead + сетка виджетов**

Заголовок → `AuroraPageHead title="Дашборд" subtitle="Quarterly overview"`. Сетка виджетов — Aurora-grid (CSS grid в `GlassCard`).

- [ ] **Step 2: W1 (KPI per-project)**

Каждый KPI блок → `GlowRing pct={...} sub={...}` + NeonLine спарклайн (если есть тренд). Рамка — `GlassCard`.

- [ ] **Step 3: W2 (per-employee 4 роли)**

Список сотрудников → стол `.gtable`. Аватары — `Avatar`. Pill ролей.

- [ ] **Step 4: W3 (heatmap 5×N)**

Таблица heatmap → классы `.heat-over/.heat-warn/.heat-ok/.heat-good` из app.css. Числа — `.num` (JetBrains Mono).

- [ ] **Step 5: W4 (hours balance)**

Bar chart нагрузки → Recharts с `useChartTheme` (Aurora palette). Drill-in календарь — внутри AntD `Drawer` (overlay перекрасит).

- [ ] **Step 6: Recharts integration**

Все `<LineChart>/<BarChart>/<PieChart>` дашборда — пробросить:
```typescript
const ct = useChartTheme();
// ...
<CartesianGrid stroke={ct.gridStroke} />
<XAxis stroke={ct.axisColor} />
<Tooltip content={<GlassTooltip />} />
{data.map((s, i) => <Line stroke={ct.palette[i]} />)}
```

- [ ] **Step 7: Smoke + commit**

```bash
git add frontend/src/pages/DashboardPage.tsx frontend/src/components/dashboard/
git commit -m "feat(aurora): / dashboard — GlowRing KPI, NeonLine spark, heatmap, Recharts Aurora palette"
```

---

### Task 27: /executive (KPI + risks + AI summary)

**Files:**
- Modify: `frontend/src/pages/ExecutiveDashboardPage.tsx`
- Modify: `frontend/src/components/executive/KpiCard.tsx`
- Modify: `frontend/src/components/executive/RiskList.tsx`
- Modify: `frontend/src/components/executive/ModuleHealth.tsx`
- Modify: `frontend/src/components/executive/AISummary.tsx`

- [ ] **Step 1: PageHead**

`AuroraPageHead title="Сводка для руководителя"`.

- [ ] **Step 2: KpiCard → GlassCard + GlowRing**

- [ ] **Step 3: RiskList → glass-list с tone badges**

- [ ] **Step 4: ModuleHealth → Track per module**

- [ ] **Step 5: AISummary → 3 столбца GlassCard**

Fraunces для заголовков секций (`.serif`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ExecutiveDashboardPage.tsx frontend/src/components/executive/
git commit -m "feat(aurora): /executive — KPI rings, risk badges, Track health, glass AI summary"
```

---

### Task 28: /analytics (иерархический отчёт)

**Files:**
- Modify: `frontend/src/pages/AnalyticsPage.tsx` (или wrapper)
- Modify: `frontend/src/components/analytics/AnalyticsTable.tsx`
- Modify: `frontend/src/components/analytics/AnalyticsKpiTiles.tsx`
- Modify: `frontend/src/components/analytics/AnalyticsFilters.tsx`
- Modify: `frontend/src/components/analytics/AnalyticsWorklogsBlock.tsx`
- Modify: `frontend/src/components/analytics/IssueContextBlock.tsx`
- Modify: `frontend/src/components/analytics/AnalyticsDetailWorkspace.tsx`

- [ ] **Step 1: PageHead + master-detail layout**

Сохраняется master-detail. Левая колонка (filter + table) — `GlassCard`, правая (detail) — `GlassCard`.

- [ ] **Step 2: AnalyticsKpiTiles → GlowRing per metric**

- [ ] **Step 3: AnalyticsFilters → GlassInput + Segmented + Pills для активных фильтров**

- [ ] **Step 4: AnalyticsTable**

Это AntD `Table`. Overlay `antdGlass.css` уже перекрасит chrome. Дополнительно: подсветка строк выбранной — `background: color-mix(in srgb, var(--accent-1) 12%, transparent)`. Резизабельность колонок — сохраняется как есть.

- [ ] **Step 5: WorklogsBlock + IssueContextBlock**

Карточки с pill-статусами задач.

- [ ] **Step 6: Smoke + commit**

```bash
git add frontend/src/pages/AnalyticsPage.tsx frontend/src/components/analytics/
git commit -m "feat(aurora): /analytics — glass master-detail, GlowRing KPI, glass tooltip"
```

---

### Task 29: /analytics/work-type-report (+ print)

**Files:**
- Modify: `frontend/src/pages/WorkTypeReportPage.tsx`
- Modify: `frontend/src/pages/WorkTypeReportPrintPage.tsx`
- Modify: `frontend/src/components/work-type-report/*`

- [ ] **Step 1: PageHead + Toolbar**

`AuroraPageHead`. Toolbar (`Toolbar.tsx`) — Segmented + GlassButton + GlassInput для поиска.

- [ ] **Step 2: KpiRow → GlowRing row**

- [ ] **Step 3: HierarchyTable**

Таблица в стиле `.gtable`. Подсветка тем — pill с акцент-цветом.

- [ ] **Step 4: ThemeDistribution → Track per theme**

- [ ] **Step 5: AiHeadline, RecommendationCard → GlassCard**

- [ ] **Step 6: PrintView (`/print`)**

В `@media print` отключить glow/blur. Использовать чистые цвета без прозрачности.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/WorkTypeReportPage.tsx frontend/src/pages/WorkTypeReportPrintPage.tsx frontend/src/components/work-type-report/
git commit -m "feat(aurora): /work-type-report + print — GlowRing/Track/glass карточки, упрощённый print"
```

---

### Task 30: /categories (lazy tree, 4 вкладки)

**Files:**
- Modify: `frontend/src/pages/CategoriesEditorPage.tsx`
- Modify: `frontend/src/components/categories/BulkTriageDrawer.tsx`

- [ ] **Step 1: AuroraPageHead + GlassTabs (4 ключа: stack/active/archive_target/archive)**

- [ ] **Step 2: Multi-team Select + поиск**

Select остаётся AntD (overlay), поиск → `GlassInput icon={<Search />}` (Lucide).

- [ ] **Step 3: Tree**

AntD `Tree` — overlay `antdGlass.css` перекрасит фон, hover, selected. Иконки expand/collapse: оставить AntD по умолчанию (или подменить на Lucide chevron в Aurora-режиме через `switcherIcon` prop).

- [ ] **Step 4: Row tint per depth**

Уже есть классы `.tree-row-depth-0..5`. Добавить Aurora-варианты в `glass.css`:
```css
[data-theme="aurora"] .tree-row-depth-0 td { background: color-mix(in srgb, var(--accent-1) 4%, transparent); }
[data-theme="aurora"] .tree-row-depth-1 td { background: color-mix(in srgb, var(--accent-1) 8%, transparent); }
/* ... */
```

- [ ] **Step 5: BulkTriageDrawer**

AntD `Drawer` overlay. 3 секции внутри — `GlassCard` каждая.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CategoriesEditorPage.tsx frontend/src/components/categories/ frontend/src/aurora/styles/glass.css
git commit -m "feat(aurora): /categories — GlassTabs, Lucide search, tree row tints, glass drawer"
```

---

### Task 31: /resource-planning (Gantt — НАИБОЛЬШИЙ РИСК)

**Files:**
- Modify: `frontend/src/pages/ResourcePlanningPage.tsx`
- Modify: `frontend/src/components/resource-planning/GanttChart.tsx`
- Modify: `frontend/src/components/resource-planning/GanttRows.tsx`
- Modify: `frontend/src/components/resource-planning/TimelineHeader.tsx`
- Modify: `frontend/src/components/resource-planning/NonWorkingZones.tsx`
- Modify: `frontend/src/components/resource-planning/PertOverlay.tsx`
- Modify: `frontend/src/components/resource-planning/TrackGridlines.tsx`
- Modify: `frontend/src/components/resource-planning/EmployeeAvatar.tsx`
- Modify: `frontend/src/components/resource-planning/EmployeeLoadHeatmap.tsx`
- Modify: `frontend/src/components/resource-planning/BulkResetDropdown.tsx`
- Modify: `frontend/src/components/resource-planning/AppearanceModal.tsx`
- Modify: `frontend/src/components/resource-planning/sidebar/*` (5 секций)

- [ ] **Step 1: PageHead + 2-column layout**

`AuroraPageHead`. Левая колонка — `GlassCard` с Gantt. Правая sidebar — `GlassCard` с 6 секциями (каждая внутренняя — `<div className="divider">` сверху + контент).

- [ ] **Step 2: GanttChart — color tokens**

В `GanttChart.tsx`: бары задач — fill `linear-gradient(90deg, var(--accent-1), var(--accent-2))` + `box-shadow: 0 0 12px var(--accent-glow)`. Конфликтные бары — `linear-gradient(90deg, var(--bad), var(--warn))` + red glow. Pinned — `outline: 2px solid var(--accent-border)`.

- [ ] **Step 3: NonWorkingZones (weekends)**

Полупрозрачный stripe-pattern на `--glass-bg`:
```typescript
const stripeStyle = isAurora ? {
  background: 'repeating-linear-gradient(135deg, rgba(255,255,255,0.04) 0 6px, transparent 6px 12px)',
} : { /* classic */ };
```

- [ ] **Step 4: PertOverlay**

Пунктирные линии — `stroke: var(--accent-2); stroke-dasharray: 4 4; filter: drop-shadow(0 0 4px var(--accent-glow))`.

- [ ] **Step 5: TrackGridlines**

`stroke: var(--glass-border); opacity: 0.5`.

- [ ] **Step 6: EmployeeAvatar (left column)**

Заменить на `Avatar` primitive из Aurora + pill ключа Jira.

- [ ] **Step 7: EmployeeLoadHeatmap**

Каждый день — `Track pct={dayLoad} max={100}`. Цвет: `--accent-1` при <70%, `--warn` при 70-110%, `--bad` при >110%.

- [ ] **Step 8: BulkResetDropdown**

В Aurora-режиме — `GlassButton ghost` с Lucide `ChevronDown` icon.

- [ ] **Step 9: AppearanceModal**

AntD `Modal` overlay. Sliders — нативные AntD, перекрашиваются через overlay.

- [ ] **Step 10: Sidebar 6 секций**

Каждая секция — `<GlassCard padding={12}>` с заголовком `.eyebrow` и контентом. `AlgorithmSection`, `DailyBreakdownSection`, `HoursSummarySection`, `PhaseCalcSection`, `SectionVisibilityPopover` — внутри.

- [ ] **Step 11: Smoke**

Долгий ручной тест: открыть `/resource-planning`, проверить:
- Бары видны, конфликты подсвечены
- Drag operations работают
- Weekend stripes видны
- Heatmap работает
- AppearanceModal открывается и применяется
- BulkReset dropdown работает

- [ ] **Step 12: Commit**

```bash
git add frontend/src/pages/ResourcePlanningPage.tsx frontend/src/components/resource-planning/
git commit -m "feat(aurora): /resource-planning — Gantt бары + glow, stripe weekends, glass sidebar"
```

---

### Task 32: /resource-planning/compare (диф сценариев)

**Files:**
- Modify: `frontend/src/pages/ScenarioComparatorPage.tsx`

- [ ] **Step 1: 2-column GlassCard layout**

Каждая колонка сценария — `GlassCard`. Diff-индикаторы → `Pill` с tone (`bad` для удалено, `good` для добавлено, `accent` для изменено).

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/ScenarioComparatorPage.tsx
git commit -m "feat(aurora): /resource-planning/compare — glass колонки + diff pills"
```

---

## Phase 8 — Тестирование и smoke

### Task 33: Aurora E2E fixture

**Files:**
- Modify: `e2e/fixtures/` или подобное (если есть Playwright fixtures)
- Create: `e2e/aurora.spec.ts` (новый)

- [ ] **Step 1: Найти E2E конфиг**

```bash
ls e2e/
cat frontend/playwright.config.ts 2>/dev/null || cat playwright.config.ts 2>/dev/null
```

- [ ] **Step 2: Aurora-smoke spec**

`e2e/aurora.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

const PAGES = [
  { path: '/', name: 'dashboard' },
  { path: '/projects', name: 'projects' },
  { path: '/analytics', name: 'analytics' },
  { path: '/analytics/work-type-report', name: 'work-type-report' },
  { path: '/executive', name: 'executive' },
  { path: '/capacity', name: 'capacity' },
  { path: '/backlog', name: 'backlog' },
  { path: '/planning', name: 'planning' },
  { path: '/resource-planning', name: 'resource-planning' },
  { path: '/sync', name: 'sync' },
  { path: '/categories', name: 'categories' },
  { path: '/feedback', name: 'feedback' },
  { path: '/settings', name: 'settings' },
];

for (const mode of ['aurora-dark', 'aurora-light'] as const) {
  test.describe(`Aurora ${mode}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/login');
      await page.evaluate((m) => localStorage.setItem('app_theme', m), mode);
      await page.fill('input[type="email"]', 'admin@example.com');
      await page.fill('input[type="password"]', 'admin');
      await page.click('button[type="submit"]');
      await page.waitForURL('/');
    });

    for (const p of PAGES) {
      test(`${p.name} renders without errors`, async ({ page }) => {
        const errors: string[] = [];
        page.on('pageerror', (e) => errors.push(e.message));
        await page.goto(p.path);
        await page.waitForLoadState('networkidle');
        expect(errors).toHaveLength(0);
        await expect(page.locator('html[data-theme="aurora"]')).toBeVisible();
        await page.screenshot({ path: `e2e-screenshots/aurora-${mode}-${p.name}.png`, fullPage: true });
      });
    }
  });
}
```

- [ ] **Step 3: Run**

```bash
cd frontend && npm run e2e -- aurora.spec.ts
```
Expected: все страницы рендерятся без runtime-ошибок в обоих режимах.

- [ ] **Step 4: Commit**

```bash
git add e2e/aurora.spec.ts
git commit -m "test(aurora): E2E smoke — все 13 страниц × 2 режима, screenshots"
```

---

### Task 34: Regression — existing E2E в Aurora-режиме

**Files:**
- Modify: existing E2E fixtures для возможности force Aurora

- [ ] **Step 1: Запустить existing E2E с force Aurora**

В `e2e/fixtures.ts` (или подобное) добавить опцию `theme` для `beforeEach`. Пройти всем существующим спекам (`navigation`, `dashboard`, `crud-flows`, `export-downloads`) с `theme=aurora-dark`.

- [ ] **Step 2: Зафиксить падения**

Если есть селекторы по AntD-классам, заменить на `data-testid` или role-based.

- [ ] **Step 3: Commit (если были фиксы)**

```bash
git commit -m "fix(aurora): existing E2E совместимы с Aurora-режимом"
```

---

### Task 35: Full pytest + lint

- [ ] **Step 1: Backend tests**

```bash
py -3.10 -m pytest tests/ -v
```
Expected: PASS (~1100 tests).

- [ ] **Step 2: Frontend lint + build**

```bash
cd frontend && npm run lint && npm run build
```
Expected: PASS.

- [ ] **Step 3: Commit fixes (если были)**

---

## Phase 9 — Polish

### Task 36: Visual review pass

- [ ] **Step 1: Запустить dev + продемонстрировать PM все 13 страниц в обоих Aurora-режимах**

- [ ] **Step 2: Зафиксить точечные правки по списку от PM**

- [ ] **Step 3: Финальный коммит**

```bash
git commit -m "polish(aurora): точечные правки по итогам визуального ревью PM"
```

---

### Task 37: Открыть PR

- [ ] **Step 1: Push branch**

```bash
git push -u origin redesign/aurora
```

- [ ] **Step 2: gh pr create**

```bash
gh pr create --draft --title "Aurora — полный визуальный редизайн (опциональный)" --body "$(cat <<'EOF'
## Summary
- Полный визуальный редизайн фронта под референс Aurora (cyan→violet glassmorphism)
- Глобальный тумблер темы в шапке: aurora-dark ↔ aurora-light ↔ classic, persisted per-user
- Классика остаётся полностью функциональной — никаких regression
- 13 страниц переоформлены (включая Dashboard, Analytics, Resource Planning Gantt)

## Что НЕ меняется
- Все формы и их валидация
- Структура роутов, query keys, hooks
- API endpoints (кроме допустимых значений theme)
- Бизнес-логика и данные

## Test plan
- [ ] Backend pytest 1100+ passes
- [ ] Frontend lint + build passes
- [ ] E2E classic + Aurora-dark + Aurora-light passes
- [ ] Manual smoke: 13 страниц × 3 режима PM-приёмка

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Получить URL PR**

```bash
gh pr view --json url
```

---

## Self-review

После написания плана — fresh-eyes пробег:

**Spec coverage:**
- §3 Архитектура → Tasks 1-5 (theme infra), 15 (shell dispatcher) ✓
- §5 Дизайн-система Aurora → Tasks 4 (стили), 6-11 (примитивы) ✓
- §6.1 Шелл → Tasks 12-14 ✓
- §6.2 Reskin страниц → Tasks 18-32 (15 страниц закрыты) ✓
- §6.3 Иконки → Lucide встроен в каждой shell/primitives задаче ✓
- §7 Recharts → Task 17 ✓
- §9 Тестирование → Tasks 33-35 ✓
- §10 Откат → отдельной задачи нет, но `git revert` + `gh pr close` (документировано в спеке)
- §11 DoD → Task 35 + Task 36 (manual PM smoke)

**Placeholders:** none.

**Type consistency:**
- `GlassCard` props одинаковы между Task 7 и Tasks 18-32 ✓
- `GlassButton.variant` consistent ✓
- `ThemeContext.isAurora` / `mode` использовано везде согласно Task 5 ✓

**Scope:** 37 задач, большой план, но cohesive — один редизайн.
