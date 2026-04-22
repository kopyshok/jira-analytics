# Planning Scenarios Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Устранить дублирование блока «разбивка ресурса по ролям», добавить отпуска в верхнюю таблицу, сделать её сворачиваемой, и выровнять вкладки над двуколоночным лейаутом.

**Architecture:** Три изолированных изменения в двух компонентах + одна перестановка в странице. Бэкенд и API не меняются — все данные уже приходят в существующих полях `ResourceSummaryOut`.

**Tech Stack:** React 19, TypeScript, Ant Design 6, inline styles (проект не использует CSS-модули)

**Spec:** `docs/superpowers/specs/2026-04-22-planning-scenarios-redesign.md`

---

## File Map

| Файл | Что меняем |
|------|-----------|
| `frontend/src/components/planning/PlanningCapacityPanel.tsx` | Удалить `ResourceBreakdownTable` и `<Collapse>` |
| `frontend/src/components/planning/ScenarioResourceSummary.tsx` | Добавить блок отпусков + collapse-логику |
| `frontend/src/pages/PlanningPage.tsx` | Вынести вкладки над сеткой, убрать `<Tabs>` |

---

## Task 1: Удалить «Разбивка по ролям» из PlanningCapacityPanel

**Files:**
- Modify: `frontend/src/components/planning/PlanningCapacityPanel.tsx`

- [ ] **Step 1.1: Удалить функцию ResourceBreakdownTable**

Удали весь блок с `function ResourceBreakdownTable` — строки 37–215. Это внутренняя функция, которая объявлена до `export default function PlanningCapacityPanel`.

После удаления файл должен начинаться с:
```typescript
import React, { useMemo } from 'react';
import { Card, Select, Skeleton, Tag } from 'antd';   // Collapse убран
// ... остальные импорты без изменений
```

- [ ] **Step 1.2: Убрать `Collapse` из импорта antd**

Строка 2 до:
```typescript
import { Card, Collapse, Select, Skeleton, Tag } from 'antd';
```

Строка 2 после:
```typescript
import { Card, Select, Skeleton, Tag } from 'antd';
```

- [ ] **Step 1.3: Удалить блок `<Collapse>` из gauge-карточки**

Найди в теле `PlanningCapacityPanel` блок (сейчас около строк 352–362):
```tsx
        {summary && (
          <Collapse
            ghost
            style={{ marginTop: 8 }}
            items={[{
              key: 'breakdown',
              label: <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>Разбивка по ролям ↓</span>,
              children: <ResourceBreakdownTable summary={summary} />,
            }]}
          />
        )}
```

Удали этот блок целиком. Карточка должна заканчиваться прогресс-баром:
```tsx
        <div style={{ position: 'relative', height: 14, background: DARK_THEME.darkAccent, borderRadius: 7, overflow: 'hidden' }}>
          <div
            style={{
              position: 'absolute', left: 0, top: 0, bottom: 0,
              width: `${plannedPct}%`,
              background: overallOver ? DARK_THEME.amber : DARK_THEME.cyanPrimary,
              transition: 'width .2s',
            }}
          />
        </div>
      </Card>
```

- [ ] **Step 1.4: Проверить компиляцию**

```bash
cd frontend && npx tsc --noEmit
```

Ожидается: 0 ошибок.

- [ ] **Step 1.5: Commit**

```bash
git add frontend/src/components/planning/PlanningCapacityPanel.tsx
git commit -m "feat(planning): remove ResourceBreakdownTable collapse from capacity panel"
```

---

## Task 2: Добавить блок «Отпуска» в ScenarioResourceSummary

**Files:**
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx`

Данные уже приходят в `summary.absence_days_by_employee: Array<{ employee_id, display_name, role: string|null, days: number }>`.

- [ ] **Step 2.1: Добавить `useState` в импорт React**

Строка 1 до:
```typescript
import React, { useMemo } from 'react';
```

Строка 1 после:
```typescript
import React, { useMemo, useState } from 'react';
```

- [ ] **Step 2.2: Обернуть существующее содержимое карточки в flex-контейнер**

В функции `ScenarioResourceSummary`, в блоке `return`, оберни всё что сейчас внутри `<Card>` в `<div style={{ display: 'flex' }}>`. Карточка сейчас содержит: header-строку, строку «Нормированные работы», строки обязательных работ, строку «На бэклог». Все они должны быть в левой части flex.

Замени:
```tsx
  return (
    <Card styles={{ body: { padding: 0, overflow: 'hidden', borderRadius: 8 } }}>
      {/* Header row */}
      <div style={headerStyle}>
        ...
      </div>
      {/* ... остальные строки ... */}
    </Card>
  );
```

На:
```tsx
  return (
    <Card styles={{ body: { padding: 0, overflow: 'hidden', borderRadius: 8 } }}>
      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        {/* Основная таблица */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Header row */}
          <div style={headerStyle}>
            ...
          </div>
          {/* ... остальные строки без изменений ... */}
        </div>

        {/* Блок отпусков — добавляется в Step 2.3 */}
      </div>
    </Card>
  );
```

- [ ] **Step 2.3: Добавить блок отпусков**

Добавь секцию отпусков после закрывающего `</div>` основной таблицы, внутри flex-контейнера. Вставить нужно перед закрывающим `</div>` flex-обёртки:

```tsx
        {/* Блок отпусков */}
        {summary.absence_days_by_employee.length > 0 && (
          <div style={{
            borderLeft: `2px solid ${DARK_THEME.border}`,
            background: DARK_THEME.darkAccent,
            minWidth: 180,
            maxWidth: 240,
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
          }}>
            {/* Заголовок */}
            <div style={{
              padding: '8px 12px',
              borderBottom: `1px solid ${DARK_THEME.border}`,
              fontSize: 10,
              color: DARK_THEME.textMuted,
              textTransform: 'uppercase' as const,
              letterSpacing: 0.5,
              fontWeight: 600,
              background: DARK_THEME.cardBg,
            }}>
              Отпуска квартала
            </div>
            {/* Список сотрудников */}
            <div style={{ padding: '6px 12px', flex: 1 }}>
              {summary.absence_days_by_employee.map((emp) => {
                const roleColor = emp.role ? getRoleColor(roles, emp.role) : DARK_THEME.textDim;
                return (
                  <div key={emp.employee_id} style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '3px 0',
                    borderBottom: `1px solid rgba(255,255,255,0.04)`,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
                      <div style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: roleColor,
                        flexShrink: 0,
                      }} />
                      <span style={{
                        fontSize: 11,
                        color: DARK_THEME.textSecondary,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap' as const,
                      }}>
                        {emp.display_name}
                      </span>
                    </div>
                    <span style={{ fontSize: 11, fontFamily: FONTS.mono, color: DARK_THEME.textMuted, marginLeft: 8, flexShrink: 0 }}>
                      {emp.days > 0 ? `${emp.days} дн` : '—'}
                    </span>
                  </div>
                );
              })}
            </div>
            {/* Итого */}
            {(() => {
              const totalDays = summary.absence_days_by_employee.reduce((s, e) => s + e.days, 0);
              const totalVacHours = Math.round(
                Object.values(summary.calendar_gross_by_role).reduce((s, v) => s + v, 0) -
                Object.values(summary.total_by_role).reduce((s, v) => s + v, 0)
              );
              return totalDays > 0 ? (
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '6px 12px',
                  borderTop: `1px solid ${DARK_THEME.border}`,
                  fontSize: 11,
                }}>
                  <span style={{ color: DARK_THEME.textMuted }}>Итого</span>
                  <span style={{ fontFamily: FONTS.mono, color: DARK_THEME.textSecondary }}>
                    {totalDays} дн · −{totalVacHours} ч
                  </span>
                </div>
              ) : null;
            })()}
          </div>
        )}
```

- [ ] **Step 2.4: Проверить компиляцию**

```bash
cd frontend && npx tsc --noEmit
```

Ожидается: 0 ошибок.

- [ ] **Step 2.5: Проверить визуально**

Запусти сервер если не запущен:
```bash
cd frontend && npm run dev
```

Открой http://localhost:5173 → Сценарии. Выбери сценарий с командой. Убедись:
- Верхняя таблица показывает блок отпусков справа от «Итого»
- В правом блоке коллапса «Разбивка по ролям ↓» больше нет

- [ ] **Step 2.6: Commit**

```bash
git add frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): add vacation block to resource summary table"
```

---

## Task 3: Сделать таблицу ресурса сворачиваемой

**Files:**
- Modify: `frontend/src/components/planning/ScenarioResourceSummary.tsx`

- [ ] **Step 3.1: Добавить collapse-состояние с localStorage**

Сразу после объявления `const { data: roles = [] } = useRoles();` добавь:

```typescript
  const LS_KEY = 'planning_resource_table_collapsed';
  const [collapsed, setCollapsed] = useState<boolean>(() => localStorage.getItem(LS_KEY) === 'true');

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(LS_KEY, String(next));
      return next;
    });
  };
```

- [ ] **Step 3.2: Добавить рендер свёрнутого состояния**

После блока `if (!summary || summary.roles.length === 0) return null;` и перед `const gridCols = ...` добавь свёрнутый рендер:

```tsx
  if (collapsed) {
    return (
      <Card styles={{ body: { padding: 0, overflow: 'hidden' } }}>
        <div style={{ display: 'flex', alignItems: 'center', height: 40 }}>
          <div style={{
            padding: '0 14px',
            fontSize: 12,
            color: DARK_THEME.textMuted,
            borderRight: `1px solid ${DARK_THEME.border}`,
            background: DARK_THEME.darkAccent,
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            whiteSpace: 'nowrap' as const,
          }}>
            На бэклог
          </div>
          {summary.roles.map((role) => (
            <div key={role} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '0 16px',
              borderRight: `1px solid ${DARK_THEME.border}`,
              height: '100%',
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: getRoleColor(roles, role) }}>
                {getRoleLabel(roles, role)}
              </span>
              <span style={{ fontSize: 14, fontWeight: 700, fontFamily: FONTS.mono, color: DARK_THEME.cyanPrimary }}>
                {Math.round(summary.available_for_backlog_by_role[role] ?? 0)} ч
              </span>
            </div>
          ))}
          <div style={{
            padding: '0 16px',
            borderRight: `1px solid ${DARK_THEME.border}`,
            height: '100%',
            display: 'flex',
            alignItems: 'center',
          }}>
            <span style={{ fontSize: 15, fontWeight: 700, fontFamily: FONTS.mono, color: DARK_THEME.cyanPrimary }}>
              {Math.round(summary.available_for_backlog_total)} ч
            </span>
          </div>
          <button
            onClick={toggleCollapsed}
            style={{
              marginLeft: 'auto',
              padding: '0 14px',
              height: '100%',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: 11,
              color: DARK_THEME.textMuted,
            }}
          >
            ↓ Развернуть
          </button>
        </div>
      </Card>
    );
  }
```

- [ ] **Step 3.3: Добавить кнопку «Свернуть» в развёрнутое состояние**

В `res-expand-header` (заголовок карточки в развёрнутом виде) — добавь кнопку «Свернуть». Найди место где рендерится `headerStyle` (первый `<div style={headerStyle}>`) и перед ним добавь строку-шапку:

Добавь перед `{/* Header row */}` внутри основной таблицы (`<div style={{ flex: 1, minWidth: 0 }}>`) небольшую строку с кнопкой — это нужно вставить в самое начало, до `headerStyle`:

```tsx
          {/* Кнопка свернуть — всегда над таблицей */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            padding: '4px 10px',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            background: DARK_THEME.cardBg,
          }}>
            <button
              onClick={toggleCollapsed}
              style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                fontSize: 11,
                color: DARK_THEME.textMuted,
                padding: '2px 4px',
              }}
            >
              ↑ Свернуть
            </button>
          </div>
```

- [ ] **Step 3.4: Проверить оба состояния**

```bash
cd frontend && npx tsc --noEmit
```

Открой http://localhost:5173 → Сценарии. Проверь:
- Кнопка «↑ Свернуть» сворачивает таблицу до одной строки с цифрами «На бэклог»
- Кнопка «↓ Развернуть» раскрывает обратно
- После перезагрузки страницы состояние сохранилось (localStorage)

- [ ] **Step 3.5: Commit**

```bash
git add frontend/src/components/planning/ScenarioResourceSummary.tsx
git commit -m "feat(planning): collapsible resource summary table with localStorage persistence"
```

---

## Task 4: Вынести вкладки над двуколоночным лейаутом

**Files:**
- Modify: `frontend/src/pages/PlanningPage.tsx`

- [ ] **Step 4.1: Добавить state активной вкладки**

Найди блок объявления `useState` в начале `PlanningPage`. После `const [createOpen, setCreateOpen] = useState(false);` добавь:

```typescript
  const [activeTab, setActiveTab] = useState<'distribution' | 'rules'>('distribution');
```

- [ ] **Step 4.2: Убрать `Tabs` из импортов antd**

В верхней части файла найди строку:
```typescript
import {
  Alert, App, Badge, Button, Card, Checkbox, Popconfirm, Select, Space, Tabs, Tag, Tooltip,
} from 'antd';
```

Замени на:
```typescript
import {
  Alert, App, Badge, Button, Card, Checkbox, Popconfirm, Select, Space, Tag, Tooltip,
} from 'antd';
```

- [ ] **Step 4.3: Заменить `<Tabs>` + левую колонку на custom tab bar + conditional content**

Найди в JSX блок (около строки 319):
```tsx
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'stretch' }}>
            <Tabs
              defaultActiveKey="distribution"
              items={[
                {
                  key: 'distribution',
                  label: 'Распределение',
                  children: (
                    <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                    <Card
                      ...вся карточка бэклога...
                    </Card>
                    </div>
                  ),
                },
                {
                  key: 'rules',
                  label: 'Правила',
                  children: (
                    <Card
                      title="Правила обязательных работ"
                      ...
                    >
                      <ScenarioRulesEditor scenarioId={scenarioId} />
                    </Card>
                  ),
                },
              ]}
            />

            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              ...правый блок...
            </Space>
          </div>
```

Замени на:
```tsx
          {/* Вкладки — на всю ширину над сеткой */}
          <div style={{
            display: 'flex',
            borderBottom: `1px solid ${DARK_THEME.border}`,
            marginBottom: 0,
          }}>
            {(['distribution', 'rules'] as const).map((key) => (
              <div
                key={key}
                onClick={() => setActiveTab(key)}
                style={{
                  padding: '8px 16px',
                  cursor: 'pointer',
                  fontSize: 14,
                  borderBottom: activeTab === key ? `2px solid ${DARK_THEME.cyanPrimary}` : '2px solid transparent',
                  marginBottom: -1,
                  color: activeTab === key ? DARK_THEME.cyanPrimary : DARK_THEME.textMuted,
                  transition: 'color .15s',
                  userSelect: 'none' as const,
                }}
              >
                {key === 'distribution' ? 'Распределение' : 'Правила'}
              </div>
            ))}
          </div>

          {/* Двуколоночная сетка — оба блока выровнены по верху */}
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 460px', gap: 16, alignItems: 'start' }}>
            {/* Левая колонка — контент активной вкладки */}
            {activeTab === 'distribution' ? (
              <Card
                title="Элементы бэклога"
                styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column', flex: 1 } }}
                style={{ display: 'flex', flexDirection: 'column', flex: 1 }}
                loading={allocLoading}
                extra={
                  <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                    {isApproved
                      ? 'сценарий утверждён — отметки заблокированы'
                      : 'клик по строке переключает включение'}
                  </span>
                }
              >
                {/* === СКОПИРУЙ СЮДА СОДЕРЖИМОЕ children 'distribution' БЕЗ ОБЁРТКИ <div> === */}
                {/* Это весь блок с gridTemplateColumns=GRID (заголовок таблицы) и список allocations */}
              </Card>
            ) : (
              <Card
                title="Правила обязательных работ"
                styles={{ body: { padding: 14 } }}
                style={{ background: DARK_THEME.cardBg }}
              >
                <ScenarioRulesEditor scenarioId={scenarioId} />
              </Card>
            )}

            {/* Правая колонка — без изменений */}
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              <PlanningCapacityPanel
                resourceBase={resourceBase}
                allocations={allocations ?? []}
                quarter={String(quarterInt)}
                scenarioId={scenarioId}
                summary={resourceSummary}
              />
              <Card size="small" styles={{ body: { padding: 12 } }}>
                <ExternalQaInput
                  scenarioId={scenarioId}
                  value={scenario.external_qa_hours}
                  disabled={!isDraft}
                />
              </Card>
            </Space>
          </div>
```

> **Примечание:** в блоке `activeTab === 'distribution'` нужно перенести содержимое `children` карточки бэклога — это `<div style={{ display: 'grid', gridTemplateColumns: GRID, ... }}>` (заголовок) и `<div style={{ overflowY: 'auto', flex: 1 }}>` со списком allocations. Просто скопируй их из старого `children` в `distribution` внутрь нового `<Card>` как его прямых потомков.

- [ ] **Step 4.4: Проверить компиляцию**

```bash
cd frontend && npx tsc --noEmit
```

Ожидается: 0 ошибок. Если `Tabs` не используется нигде ещё — компилятор не ругнётся на удалённый импорт (но TypeScript не следит за неиспользуемыми импортами — это сделает ESLint).

```bash
cd frontend && npm run lint
```

- [ ] **Step 4.5: Проверить визуально**

Открой http://localhost:5173 → Сценарии. Убедись:
- Вкладки «Распределение» / «Правила» на всю ширину над сеткой
- Карточка «Элементы бэклога» и правый блок «Ресурс команды» начинаются с одной линии
- Переключение вкладок работает
- При вкладке «Правила» правый блок продолжает показываться

- [ ] **Step 4.6: Commit**

```bash
git add frontend/src/pages/PlanningPage.tsx
git commit -m "feat(planning): move tabs above two-col grid to fix vertical alignment"
```

---

## Task 5: Smoke-тест и пуш

- [ ] **Step 5.1: Полный прогон E2E**

```bash
cd frontend && npx playwright test --project=chromium e2e/navigation.spec.ts e2e/dashboard.spec.ts
```

Ожидается: все тесты пройдены. E2E покрывает навигацию; визуальный регресс Planning проверяется вручную.

- [ ] **Step 5.2: Финальная визуальная проверка**

Открой http://localhost:5173 → Сценарии. Проверь по чек-листу:
- [ ] Верхняя таблица: колонки ролей с цветами, строки обязательных работ, строка «На бэклог» подсвечена
- [ ] Блок отпусков: список сотрудников с цветными точками, итоговая строка
- [ ] Кнопка «↑ Свернуть» → таблица схлопывается в одну строку с часами по ролям
- [ ] Кнопка «↓ Развернуть» → таблица раскрывается
- [ ] После перезагрузки состояние свёрнутости сохранилось
- [ ] Правый блок: нет кнопки «Разбивка по ролям ↓»
- [ ] Вкладки на всю ширину, выровнены с верхом обоих блоков
- [ ] Переключение «Распределение» ↔ «Правила» работает

- [ ] **Step 5.3: Push**

```bash
git push origin main
```
