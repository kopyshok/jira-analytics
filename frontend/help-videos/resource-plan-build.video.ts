// Ролик «Как построить ресурсный план и прочитать его»: утверждённый сценарий →
// «Распределить» → статус «Готово» и метки качества → виды «Задачи»/«Исполнители»,
// фильтр «Исполнители», масштаб, окно «Вид» (рабочие дни, эстафета, свернуть все,
// цвета) → карточка фазы (разбор расчёта) → «Загрузка сотрудников по дням».
// Данные готовятся в beforeAll — запись идёт с момента открытия окна.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { TEAM } from './rp-setup.ts';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };

const OTHER_TEAM = 'Команда Эта';
let scenarioLabel = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const rp = `${api}/resource-planning`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  // В шапке две команды — список сценариев покажет их группами.
  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM, OTHER_TEAM], subgroups: [] } }));
  // Секции разбора карточки фазы скрыты заранее — в ролике их включает шестерёнка.
  ok(await request.patch(`${rp}/preferences`, {
    data: {
      view_mode: 'tasks',
      hide_weekends: false,
      collapsed_initiative_ids: [],
      detail_sections_visible: {
        algorithm: false, day_table: false, absences: false, sources: false, duration: false, critical_path: false,
      },
      detail_sections_collapsed: {},
    },
  }));

  const scenarios: Scenario[] = await (
    await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } })
  ).json();
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);
  scenarioLabel = `${scenario.quarter} ${scenario.year} — ${scenario.name}`;

  // Существующий план сценария удаляем — ролик строит план заново, с нуля.
  for (let i = 0; i < 20; i++) {
    const plans: Plan[] = await (await request.get(`${rp}/resource-plans`, { params: { team: TEAM } })).json();
    const plan = plans.find((p) => p.scenario_id === scenario.id);
    if (!plan) break;
    ok(await request.delete(`${rp}/resource-plans/${plan.id}`));
  }

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  // Секции разбора карточки фазы возвращаем к настройке по умолчанию (все видны) —
  // другие ролики раздела открывают карточку, ожидая её обычный вид.
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  // Шапка — на «Команда Альфа» без групп: так её ждут остальные ролики раздела.
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.patch(`${api}/resource-planning/preferences`, {
    data: {
      detail_sections_visible: {
        algorithm: true, day_table: true, absences: true, sources: true, duration: true, critical_path: true,
      },
      detail_sections_collapsed: {},
      hide_weekends: false,
    },
  });
  await request.dispose();
});

test('resource-plan-build', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/resource-planning', 'Как построить ресурсный план и прочитать его');
  const select = page.locator('[data-tour="rp-scenario-select"]');
  await expect(select).toBeVisible();
  await expect(page.getByText('Выберите план или создайте его из утверждённого сценария')).toBeVisible();
  await d.pause(600);
  await d.poster();
  await d.pause(900);

  await d.caption('План строится из утверждённого сценария — выберите его в списке');
  await d.click(select);
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await d.caption('При нескольких командах в шапке сценарии идут группами');
  await d.show(dropdown);
  await d.pause(300);
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: scenarioLabel }),
  );

  const status = (text: string) => page.locator('.ant-tag', { hasText: new RegExp(`^${text}$`) });
  const gantt = page.locator('[data-tour="rp-gantt"]');
  await expect(status('Черновик')).toBeVisible();
  await expect(gantt).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(500);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await expect(status('Готово')).toBeVisible({ timeout: 60_000 });
  const bars = page.locator('[data-testid^="rp-bar-"]');
  await expect(bars.first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('Сервис разложил фазы по исполнителям и дням');
  await d.pause(700);

  await d.caption('Метки качества — перегрузки, просрочки, средняя загрузка');
  await d.show(
    page.locator('.ant-tag', { hasText: /^Перегрузки:/ }),
    page.locator('.ant-tag', { hasText: /^Утилизация:/ }),
  );
  await d.pause(700);

  // Виды «Задачи» / «Исполнители».
  const layoutSwitch = page.locator('[data-tour="rp-layout-switch"]');
  await d.click(layoutSwitch.locator('.ant-segmented-item', { hasText: 'Исполнители' }), 'Вид «Исполнители» — план по людям, а не по задачам');
  await expect(page.getByText('Все работы').first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(600);
  await d.click(layoutSwitch.locator('.ant-segmented-item', { hasText: 'Задачи' }), 'Вид «Задачи» — обратно к задачам');
  await expect(bars.first()).toBeVisible();
  await page.mouse.move(900, 120);

  // Фильтр «Исполнители».
  const filter = page.locator('[data-tour="rp-people-filter"]');
  await d.click(filter, 'Фильтр «Исполнители» оставляет только выбранных людей');
  const firstOption = page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();
  await d.click(firstOption);
  await page.keyboard.press('Escape');
  await page.mouse.move(900, 120);
  await d.pause(600);
  await d.click(filter.locator('.ant-select-clear'));
  await page.mouse.move(900, 120);

  // Масштаб.
  const scaleSwitch = page.locator('[data-tour="rp-scale"]');
  await d.click(scaleSwitch.locator('.ant-segmented-item', { hasText: 'Месяц' }), 'Масштаб — от месяцев до отдельных дней');
  await d.pause(500);
  await d.click(scaleSwitch.locator('.ant-segmented-item', { hasText: 'Неделя' }));

  // Кнопка «Вид»: рабочие дни, эстафета, свернуть все, цвета.
  const viewBtn = page.locator('[data-tour="rp-view"]');
  await d.click(viewBtn, 'В окне «Вид» — ещё настройки: рабочие дни, эстафета, цвета');
  const popover = page.locator('.ant-popover:visible');
  await d.show(popover);
  await d.pause(700);
  await d.click(popover.locator('label', { hasText: 'Только рабочие дни' }), '«Только рабочие дни» убирает выходные');
  await page.mouse.move(900, 120);
  await d.pause(500);

  const relay = popover.locator('label', { hasText: 'Стрелки эстафеты' });
  await d.caption('«Стрелки эстафеты» — переход аналитика к следующей задаче');
  await d.show(relay);

  await d.click(popover.locator('button', { hasText: 'Цвета' }), '«Цвета» — своя палитра диаграммы');
  const colorsModal = page.locator('.ant-modal', { hasText: 'Цвета планировщика' });
  await expect(colorsModal).toBeVisible();
  await d.show(colorsModal);
  await d.pause(600);
  await d.click(colorsModal.getByRole('button', { name: 'Отмена' }));
  await expect(colorsModal).toBeHidden();
  // Открытие модального окна «Цвета» само закрывает всплывающую панель «Вид».
  if (await popover.isVisible()) {
    await d.click(viewBtn);
  }
  await page.mouse.move(900, 120);

  // Карточка фазы: разбор расчёта.
  await d.click(bars.first(), 'Щёлкните по полосе фазы — откроется карточка');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  await d.caption('Перенесённая вручную фаза получает метку «Закреплено»');
  const reserve = drawer.getByText(/Резерв:/);
  await reserve.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('Резерв — запас в днях; у фаз критического пути он нулевой');
  await d.show(reserve);
  await d.pause(500);
  const gear = drawer.getByRole('button', { name: 'setting' });
  await d.click(gear, 'Шестерёнка включает секции разбора расчёта');
  const secPopover = page.locator('.ant-popover:visible', { hasText: 'Показывать секции' });
  await d.click(secPopover.locator('label', { hasText: 'Дни × часы' }));
  await d.click(gear);
  await expect(secPopover).toBeHidden();

  const dayTable = drawer.getByText('Дни × часы').last();
  await dayTable.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('Дни и часы, по которым разложена работа');
  await d.show(dayTable);
  await d.pause(1000);

  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  // Загрузка сотрудников по дням.
  const load = page.locator('[data-tour="rp-load"]');
  await load.evaluate((el) => {
    (el as HTMLElement).style.marginBottom = '160px';
  });
  await d.caption('Внизу — загрузка каждого сотрудника по дням');
  await load.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await d.pause(600);
  await d.show(load);
  await d.pause(1300);

  await d.caption('Готово', 2200);
  await d.save('resource-plan-build');
});
