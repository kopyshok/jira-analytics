// Ролик «Как начать: команда, период, справка»: шапка приложения — общий
// фильтр команды (включая переключение на команду с группами и обратно),
// период (год/квартал/месяц), индикатор синхронизации, справка раздела
// (в т.ч. карточка ролика в ней), «Первые шаги», тема оформления. Отдельная
// подпись показывает, что команда и период меняют цифры во всех разделах —
// на примере плитки Дашборда.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const TEAM_WITH_GROUPS = 'Команда Эта';
const YEAR = 2026;
const QUARTER = 3;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } }));
  ok(await request.put(`${api}/users/me/theme`, { data: { theme: 'aurora-dark' } }));
  // «Первые шаги» должна быть видна в шапке — сбрасываем личный прогресс
  // «Знакомства», чтобы кнопка не спряталась из-за прошлых прогонов.
  ok(await request.put(`${api}/onboarding/me`, { data: { completed_tours: [], hidden: false } }));

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  // Возвращаем шапку к базовому состоянию для остальных роликов: своя команда
  // без групп, наш квартал, тёмная тема.
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } });
  await request.put(`${api}/users/me/theme`, { data: { theme: 'aurora-dark' } });
  await request.dispose();
});

test('start-header', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/', 'Как начать: команда, период, справка');
  const kpiFactTile = page.locator('[data-testid="dash-kpi-tile"]', { hasText: 'ВСЕГО ФАКТОМ' });
  await expect(kpiFactTile).toBeVisible({ timeout: 20_000 });
  await d.pause(700);
  await d.poster();
  await d.pause(1000);

  await d.caption('Слева — когда в последний раз обновлялись данные из Jira');
  await d.show(page.locator('[data-testid="sync-indicator"]'));
  await d.pause(1000);

  // Команда: переключение на команду с группами.
  const teamButton = page.locator('[data-tour="header-team"] button');
  await d.click(teamButton, 'Команда — тут выбирается, чьи данные видны во всех разделах');
  let popover = page.locator('.ant-popover:visible');
  await d.click(popover.getByRole('button', { name: 'Сбросить' }));
  await d.type(popover.getByPlaceholder('Поиск команды'), 'Эта', 'Найдите нужную команду поиском');
  const etaOption = popover.locator('[data-testid="team-filter-option"]', { hasText: TEAM_WITH_GROUPS });
  await d.click(etaOption, 'У этой команды есть деление на группы');
  const subgroupBlock = popover.locator('[data-testid="team-filter-subgroups"]');
  await expect(subgroupBlock).toBeVisible();
  await d.caption('Появился второй уровень фильтра — Группы');
  await d.show(subgroupBlock);
  await d.pause(1000);
  await d.click(popover.getByRole('button', { name: 'Применить' }), 'Примените выбор');

  await expect(page.getByRole('button', { name: new RegExp(TEAM_WITH_GROUPS) })).toBeVisible({ timeout: 15_000 });
  await expect(kpiFactTile).toBeVisible({ timeout: 15_000 });
  await d.caption('Дашборд сразу пересчитался под другую команду');
  await d.show(kpiFactTile);
  await d.pause(1000);

  // Вернуться к своей команде.
  await d.click(page.locator('[data-tour="header-team"] button'), 'Вернёмся к своей команде');
  popover = page.locator('.ant-popover:visible');
  await d.click(popover.getByRole('button', { name: 'Сбросить' }));
  await d.type(popover.getByPlaceholder('Поиск команды'), 'Альфа', 'Выберите обратно «Команда Альфа»');
  await d.click(popover.locator('[data-testid="team-filter-option"]', { hasText: TEAM }));
  await d.click(popover.getByRole('button', { name: 'Применить' }));
  await expect(page.getByRole('button', { name: new RegExp(TEAM) })).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(1100, 140);

  // Период: год, квартал, месяц.
  const periodSelects = page.locator('[data-tour="header-period"] .ant-select');
  await d.click(periodSelects.nth(1), 'Период — год, квартал и месяц — тоже общий на все разделы');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Q2 \(/ }));
  await expect(kpiFactTile).toBeVisible({ timeout: 15_000 });
  await d.caption('Смените квартал — и цифры на дашборде пересчитаются');
  await d.show(kpiFactTile);
  await d.pause(1000);
  await d.point(periodSelects.nth(2));
  await d.caption('Можно смотреть весь квартал или один его месяц');
  await page.mouse.move(1100, 140);
  await d.pause(600);

  // Справка раздела.
  await d.click(page.locator('[data-tour="header-help"] button'), 'Кнопка «?» открывает справку текущего раздела');
  let drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await d.pause(1000);
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'У каждого раздела своя справка — например, у «Ресурсов»');
  await d.click(page.locator('[data-tour="header-help"] button'));
  drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  const videoCard = drawer.getByRole('button', { name: /Смотреть видео/ }).first();
  await expect(videoCard).toBeVisible();
  await d.caption('В справке разделов иногда есть короткие ролики — вот такая карточка');
  await d.show(videoCard);
  await d.pause(900);
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  await d.click(page.locator('.side-item', { hasText: 'Дашборд' }), 'Вернёмся на Дашборд');

  // Первые шаги.
  await d.click(page.locator('[data-tour="header-onboarding"]'), 'Кнопка «Первые шаги» — чек-лист настройки и знакомство с сервисом');
  drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await d.caption('Сверху — шаги настройки команды');
  await d.show(drawer.getByText('Настройка команды', { exact: true }));
  await d.pause(1100);
  const introHeading = drawer.getByText('Знакомство с сервисом', { exact: true });
  await introHeading.scrollIntoViewIfNeeded();
  await d.caption('А ниже — знакомство с самим сервисом');
  await d.show(introHeading);
  await d.pause(900);
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();

  // Тема оформления.
  const themeSelect = page.locator('.topbar .ant-select', { hasText: 'Aurora' });
  await d.click(themeSelect, 'Тему оформления можно сменить');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Aurora светлая' }));
  await d.pause(900);
  await d.click(themeSelect, 'Вернём тёмную');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Aurora тёмная' }));
  await d.pause(600);

  await d.show(page.locator('[data-tour="dash-projects"]'));
  await d.caption('Готово', 2200);
  await d.save('start-header');
});
