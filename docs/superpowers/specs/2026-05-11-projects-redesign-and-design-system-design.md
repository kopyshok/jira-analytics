# Дизайн: /projects редизайн (B) + Design System overhaul (D)

**Статус:** draft
**Дата:** 2026-05-11
**Автор:** Claude (Opus 4.7) под руководством PM
**Связанные коммиты предыстории:** 0a7094f, 1e9b34d, dca5e64, db94346 (Impeccable detect fixes + CI gate + AntD message migration + token sweep batch 1)

## 1. Контекст и мотивация

Impeccable-аудит (2026-05-11) трёх страниц вскрыл два системных провала:

| Страница | Health Score |
|---|---|
| /projects (детали проекта) | **6/20** (Poor) |
| / (Dashboard) | 8/20 (Poor) |
| /executive | 10/20 (Acceptable) |

Худшая — `/projects`. Конкретные проблемы:

- Hero-блок презентации = три KPI-плитки «Часов / Задач / Участников» — каноническая «AI-дашборд» композиция. Узнаётся как сгенерированный интерфейс с одного взгляда.
- 16 файлов раздела не импортируют ни одного токена темы — везде хардкод hex-литералов (`#0d1c33`, `#7e94b8` и т.д.). Переключатель тем (есть в настройках, 4 темы) на этой странице не работает в принципе.
- Дублированные палитры серийных цветов (`AI_PALETTE`, `COLORS`, `AVATAR_COLORS`, `GOAL_COLORS`) — копипаста в 4 файлах.
- Жёстко зашитые ширины (`width: 360`, `gridTemplateColumns: '1fr 1fr'`, `height: calc(100vh - 64px)`) ломают вёрстку на узких окнах и мобильных.
- Кнопка PNG-экспорта использует `html2canvas` с 800мс `setTimeout` race + scale 2 на всю страницу — морозит вкладку, иногда снимает пустой результат до завершения анимаций Recharts. Параллельно с этим в проекте уже выбран `window.print()` как канонический путь экспорта (CLAUDE.md).
- Тултипы метрик через нативный HTML-атрибут `title=` — не следуют теме, не доступны с клавиатуры, на одной строке.
- Логический баг в расчёте среднего рейтинга в карточке списка: проекты с одной незаполненной оценкой получают заниженное среднее.

Второй системный провал — отсутствие единой темы как архитектурного объекта. Константа `DARK_THEME` существует, но это просто snapshot тёмно-синей темы. `APP_THEMES` определяет 4 темы, но компоненты импортируют `DARK_THEME` напрямую и не реагируют на переключение. Хук `useAppTheme` существует, но используется только в `main.tsx` и `AppLayout.tsx` — все остальные компоненты обходят систему.

## 2. Цели и не-цели

### Цели

**D (Design System):**

- Перевести тему из «const с полями» в полноценную архитектуру: семантические группы токенов, реактивный хук доступа, полное покрытие AntD-провайдером.
- Сделать переключение между 4 темами рабочим на всех страницах.
- Централизовать серийные цвета графиков (палитра в одном источнике, потребляется через тему).
- Обратная совместимость: старая константа `DARK_THEME` продолжает экспортироваться (помечена deprecated, маппится на тёмно-синюю тему через адаптер). Никакого массового rewrite в один коммит.
- Линтер-правило, запрещающее хардкод hex-цветов в inline-стилях. Активируется после миграции основной массы файлов.

**B (/projects редизайн):**

- Hero-блок презентации в редакторской типографике: курсивный Fraunces заголовок, период и статус как pill-чипы, метрики растворены в одном прозаическом предложении («На проекте 8 человек работали 13 недель — записали 1 247 часов в 32 задачах»).
- Адаптивная сетка: AntD `<Row><Col>` на уровне master-detail split, CSS Grid `auto-fit` с `minmax` внутри карточек.
- Удалены параллельные массивы серийных цветов — все четыре карточки потребляют один источник из новой темы.
- Замена нативных `title=` тултипов на AntD `<Tooltip>`.
- Стабильный PNG-экспорт: отключение анимаций Recharts на момент снимка, ожидание `document.fonts.ready` + `Promise.all` загрузки картинок вместо фиксированного таймаута. Параллельно остаётся `window.print()` как второй путь экспорта (Q5 пользователь выбрал C — keep both).
- Фикс расчёта среднего рейтинга (исключать `null` из суммы и из делителя одновременно).

### Не-цели

- Compact view (табличный режим) не редизайнится — только проходит через token sweep
- Внутренние карточки детали (категории, сотрудники, цели, рейтинги, статус) — только token sweep + лёгкая адаптивность, визуальный язык неизменен
- Информационная архитектура (слияние Compact и Presentation в один view) — отвергнуто на Q2
- Кликабельные сектора donut-чарта на клавиатуре — требует форка Recharts, отложено
- Numeric scale токенов (Tailwind 50-950) — отвергнуто на Q3, semantic-only
- Полная переделка визуального языка с новой палитрой и типографикой — отвергнуто на Q1 (B option), осталось C-уровень

## 3. Архитектура темы (D)

### 3.1 Структура токенов

Тема представлена как объект с шестью семантическими группами. Все группы определены для каждой из четырёх тем.

```ts
interface ThemeTokens {
  surface: {
    page: string;     // основной фон страницы
    sidebar: string;  // боковая панель, header
    card: string;     // карточки, модалки, popover
    accent: string;   // подсветка активного элемента, hover-state
    rows: string;     // чередующиеся строки таблиц
  };
  text: {
    primary: string;    // заголовки, основной body
    secondary: string;  // body, описания
    muted: string;      // лейблы, метаданные
    hint: string;       // eyebrow, caption
    dim: string;        // disabled, placeholder
  };
  border: {
    subtle: string;   // тонкие разделители
    default: string;  // рамки карточек
  };
  accent: {
    primary: string;    // CTA, ссылки, ключевые данные
    secondary: string;  // hover, вторичные кнопки
  };
  status: {
    success: string;  // позитивный сигнал
    warning: string;  // внимание (formerly amber)
    danger: string;   // критично
    info: string;     // нейтральный инфо
  };
  chart: {
    series: string[];                              // упорядоченный список для легенды
    byRole: Record<ChartRoleKey, string>;          // именованный доступ (blue/green/orange/purple/cyan/red/neutral/yellow)
  };
}
```

`APP_THEMES` остаётся словарём из 4 тем: `dark`, `dark-blue`, `dark-slate`, `dark-charcoal`. Каждая возвращает объект `ThemeTokens`. Значения подбираются так, чтобы текущие визуальные импульсы (cyan-акцент в тёмно-синей, оранжевый в тёплой и т.д.) сохранились.

### 3.2 Хук доступа

```ts
import { useThemeTokens } from '@/hooks/useThemeTokens';

function MyComponent() {
  const t = useThemeTokens();
  return <div style={{ background: t.surface.card, color: t.text.primary }} />;
}
```

Хук читает текущую тему из `useAppTheme()` и возвращает `APP_THEMES[currentTheme].tokens`. При смене темы компоненты-потребители ре-рендерятся.

### 3.3 Обратная совместимость

Старая константа `DARK_THEME` остаётся в `utils/constants.ts`, но её значение — алиас на `APP_THEMES['dark-blue'].tokens`, проброшенный через legacy-адаптер. Адаптер мапит старые плоские ключи на новую вложенную структуру:

| Старый ключ | Новый путь |
|---|---|
| `pageBg` | `surface.page` |
| `sidebarBg` | `surface.sidebar` |
| `cardBg` | `surface.card` |
| `darkAccent` | `surface.accent` |
| `darkRows` | `surface.rows` |
| `border` | `border.default` |
| `cyanPrimary` | `accent.primary` |
| `cyanSecondary` | `accent.secondary` |
| `success` | `status.success` |
| `yellow` | `status.warning` (alias) |
| `amber` | `status.warning` (primary) |
| `amberDim` | (deprecated, маппится на `status.warning`) |
| `danger` | `status.danger` |
| `textPrimary` | `text.primary` |
| `textSecondary` | `text.secondary` |
| `textMuted` | `text.muted` |
| `textHint` | `text.hint` |
| `textDim` | `text.dim` |

`DARK_THEME` помечен `@deprecated` JSDoc-комментарием. ESLint-правило (см. §3.5) не ругается на его использование — миграция постепенная.

### 3.4 Маппинг в AntD

`ConfigProvider` в `main.tsx` расширяется на все используемые компоненты:

- `Layout`, `Menu`, `Card`, `Table`, `Modal`, `Tabs`, `Statistic`, `Typography`, `Collapse` — уже есть
- Добавляются: `Tag`, `Tooltip`, `Input`, `Select`, `DatePicker`, `Form`, `Alert`, `Notification`, `Button`, `Dropdown`, `Popover`, `Drawer`, `Spin`, `Empty`

Каждый компонент получает токены из текущей темы — фон, текст, рамка, акцент. После этого `<Tooltip>` рисуется тёмно-синим (или в цвете выбранной темы), а не дефолтным «AntD light».

### 3.5 Защита от регрессии (ESLint)

Кастомное правило `no-hex-literals-in-styles` (либо адаптация имеющегося):

- **Запрещает:** строковые литералы вида `'#RRGGBB'` или `'#RGB'` внутри объектов `style={{...}}` или `style: {...}`
- **Разрешает:** литералы в `utils/constants.ts` (источник), в массивах `chart.series` (явный whitelist), в файлах темы

Активируется после миграции основной массы (~80% файлов). До этого — отключено или работает как `warning`.

## 4. Правки /projects (B)

### 4.1 Hero-блок (вариант C — editorial typographic)

Файл: `components/projects/presentation/ProjectHero.tsx`

Полная переписка. Структура:

1. Маленький eyebrow с ключом проекта (`SVN-1247`) — не uppercase letter-spaced, обычный приглушённый.
2. Заголовок Fraunces italic, размер ~32px, цвет `text.primary`.
3. Строка под заголовком: период (`03.01 — 31.03.2025`) и статус как pill-чипы. Pill-стиль через `<Tag>` с тонкой рамкой и без фона, цвет — в зависимости от категории статуса.
4. Прозаическая сводка: «На проекте 8 человек работали 13 недель — записали 1 247 часов в 32 задачах». Текст в `text.secondary`, шрифт body, размер 14px.

Никаких KPI-плиток, никаких `BigTile` компонентов. `BigTile` удаляется.

### 4.2 Адаптивная сетка

**Уровень страницы (master + detail split):**

`pages/ProjectsPage.tsx` использует AntD `<Row gutter={[16, 16]}>` с двумя колонками:

- Master pane: `<Col xs={24} md={8} lg={6}>`
- Detail pane: `<Col xs={24} md={16} lg={18}>`

На `xs` (мобильный, <768px) — стак: список сверху, детейл снизу. На `md+` — горизонтальный split.

`ProjectsList.tsx` теряет фиксированную `width: 360`. Высота берётся из `Col`.

**Уровень карточек (внутри detail):**

`ProjectAnalysisView.tsx` использует CSS Grid `repeat(auto-fit, minmax(280px, 1fr))` вместо `1fr 1fr`. Минимум 280px на карточку, иначе сжимается в один столбец.

Внутри карточек (categories donut + bars, employees grid, top issues list) — точечно `auto-fit, minmax(...)` где сейчас фиксированные сетки.

### 4.3 Палитра графиков

Файлы, в которых сейчас локальные массивы:

- `ProjectPresentationView.tsx` (две константы: `COLORS`, `AI_PALETTE`)
- `cards/ProjectCategoriesCard.tsx` (`AI_PALETTE`)
- `cards/ProjectEmployeesCard.tsx` (`AVATAR_COLORS`)
- `cards/ProjectGoalsCard.tsx` (`GOAL_COLORS`)

Все четыре константы удаляются. Компоненты потребляют `t.chart.series` через `useThemeTokens()`.

### 4.4 Тултипы

`ProjectsWidget.tsx` (dashboard) и `CategoryWidget.tsx` (dashboard) сейчас используют HTML-атрибут `title=` для подсказок (например, имена сотрудников, краткие описания). Заменяются на AntD `<Tooltip title="...">`. Дополнительно: в `CategoryWidget.tsx` есть многострочный текст, построенный через `\n` — он не работает в нативном `title`. После замены на AntD-тултип многострочность работает через `<>`/`<br/>`.

### 4.5 Стабильный PNG-экспорт

Файл: `components/projects/ProjectHeader.tsx`, обработчик `handlePng`.

Перед снимком:

1. Переключение на Presentation view (как сейчас).
2. Отключение анимаций Recharts через временный prop (`isAnimationActive={false}` на всех `<AreaChart>`, `<BarChart>`, `<PieChart>` в дереве). Или через флаг контекста `ExportContext.exporting=true`, который компоненты-чарты читают.
3. `await document.fonts.ready` — гарантирует, что Fraunces/Manrope/JetBrains Mono загружены.
4. `await Promise.all([...imageElements].filter(img => !img.complete).map(img => new Promise(res => img.onload = img.onerror = res)))` — ожидание картинок.
5. `requestAnimationFrame` × 2 — layout flush.
6. `html2canvas` снимок.
7. Восстановление анимаций.

Никакого `setTimeout(800)`.

### 4.6 Фикс среднего рейтинга

Файл: `components/projects/ProjectListCard.tsx`, ~строки 42-46.

Текущее:

```ts
const valid = ratings.filter(v => v != null);
const avg = (r.business_value ?? 0) + (r.complexity ?? 0) + (r.priority ?? 0) / valid.length;
```

(Псевдо-код — точный участок ясен из аудита.)

Новое: сумма берётся только по `valid`, делитель — `valid.length`. Если `valid.length === 0` — показывать `—`, не делить.

## 5. Этапы реализации

**Этап 1. Foundation D**

- Расширить `utils/constants.ts`: вторая структура `THEME_TOKENS_V2` с группами. Сохраняется `APP_THEMES` (расширяется новыми группами для каждой темы), `DARK_THEME` через адаптер.
- Создать хук `hooks/useThemeTokens.ts`.
- Расширить `ConfigProvider` в `main.tsx` маппингом всех AntD-компонентов из §3.4.
- Юнит-тест на адаптер: каждый старый ключ имеет валидный новый путь.

Один коммит. Без правок существующих компонентов.

**Этап 2. /projects (B)**

Подэтапы можно делать параллельно через субагентов, но в одной ветке `main`:

- 2a. Hero редизайн + удаление `BigTile`
- 2b. Адаптивная сетка страницы + внутренних карточек
- 2c. Централизация палитры (4 файла → 1 источник из темы)
- 2d. Замена нативных тултипов на AntD `<Tooltip>` (Dashboard widgets)
- 2e. Фикс PNG-экспорта (handlePng переписан)
- 2f. Фикс бага среднего рейтинга

Каждый подэтап — отдельный коммит. После каждого — typecheck + `npm run lint:design`.

**Этап 3. Постепенная миграция страниц на новую тему**

Параллельные субагенты по страницам:

- Dashboard (3 виджета)
- Executive (5 компонентов)
- Planning, Resource Planning, Capacity, Settings — каждая отдельным субагентом

Каждый файл переписывается с `DARK_THEME.foo` на `t.bar.baz` через хук. Старая константа продолжает работать (адаптер). Можно мигрировать постепенно, по странице за релиз.

**Этап 4. Активация ESLint-правила**

После того как ≥80% файлов перешли на хук — активируется правило `no-hex-literals-in-styles`. Оставшиеся попадают под warning, фиксятся в финальном sweep.

## 6. Риски и митигации

| Риск | Митигация |
|---|---|
| Производительность ре-рендера при смене темы | Профайлинг после Этапа 2 на 3 страницах с большим деревом (Resource Planning, Capacity). Если медленно — мемоизация через `useMemo(() => tokens, [theme])` на уровне Provider. |
| Recharts серийные цвета — не реагируют на смену темы | Палитра передаётся через `tokens.chart.series` в каждом рендере (не мемоизируется по `[]`). Тест: переключение темы → цвета чартов меняются. |
| Хардкод hex в JSON-конфигах / строковых шаблонах | Линтер не покрывает. Финальная ручная вычитка перед активацией правила, плюс `git grep` по hex-паттерну. |
| Опечатки в legacy-адаптере | Юнит-тест: для каждого ключа старой константы — `expect(legacyAdapter.pageBg).toBe(THEME_TOKENS_V2['dark-blue'].surface.page)`. |
| `html2canvas` всё ещё снимает плохо | План Б — отказаться от PNG-кнопки и оставить только print (CLAUDE.md уже это рекомендует). Решение принимается после первой реализации, если результат не стабилен. |
| Импакт на E2E-тесты | `frontend/e2e/` тесты могут зависеть от CSS-селекторов или цветовых значений. Прогон полного e2e после Этапа 2. |

## 7. Открытые вопросы / отложенное

- Кликабельные сектора donut-чарта на клавиатуре — требует форка Recharts или ручного `<svg>` с keyboard handlers
- AntD-Tag-чипсы (квартал) на странице списка — keyboard a11y
- Слияние Compact + Presentation в один rich view (IA-пересмотр)
- Светлая тема — структура поддерживает, содержательно сейчас не нужна
- Numeric token scale (Tailwind 50-950) — рассмотреть при росте

## 8. Связь с Impeccable-аудитом

Этот спец закрывает следующие пункты из аудита:

| # | Аудит | Статус |
|---|---|---|
| P0 | Token bypass (Projects) | Этап 2c + Этап 3 |
| P0 | `<div onClick>` keyboard-dead | Закрыто коммитом db94346 (a11y wraps) |
| P1 | Hero KPI tile grid (AI-cliché) | Этап 2a (вариант C) |
| P1 | AntD `message` deprecated | Закрыто коммитом dca5e64 |
| P1 | Hard-coded responsive | Этап 2b |
| P1 | Дублированные палитры | Этап 2c |
| P1 | Native `title=` тултипы | Этап 2d |
| P1 | `html2canvas` PNG race | Этап 2e |
| P2 | Логический баг среднего рейтинга | Этап 2f |
| P2 | Page `<span>` вместо `<h1>` (Executive) | Закрыто коммитом db94346 |
| P2 | display:contents wrapper (Safari a11y) | Закрыто коммитом db94346 |

Не закрытые в этом этапе: status conveying только цветом (нужны глифы), uppercase eyebrow повторы (нужен экстракт `<SectionLabel>`), aria-label на custom progress bars, статус-словарь унификация (`STATUS_COLORS`/`HEALTH_COLOR`/`LEVEL_COLOR`). Это P1-P2 пункты на будущий этап.
