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
  await d.caption('Слева — время последнего обновления из Jira');
  await d.show(page.locator('[data-testid="sync-indicator"]'));
  await d.pause(600);

  // Команда: переключение на команду с группами.
  const teamButton = page.locator('[data-tour="header-team"] button');
  await d.click(teamButton, 'Команда определяет, чьи данные видны во всех разделах');
  let popover = page.locator('.ant-popover:visible');
  await d.waitVoice();
  await d.click(popover.getByRole('button', { name: 'Сбросить' }));
  await d.type(popover.getByPlaceholder('Поиск команды'), 'Эта');
  await d.caption('Можно отметить все команды сразу или только найденные');
  await d.show(popover.getByText('Выбрать найденные'));
  await d.waitVoice();
  const etaOption = popover.locator('[data-testid="team-filter-option"]', { hasText: TEAM_WITH_GROUPS });
  await d.click(etaOption, 'У этой команды есть деление на группы');
  const subgroupBlock = popover.locator('[data-testid="team-filter-subgroups"]');
  await expect(subgroupBlock).toBeVisible();
  await d.caption('Появился второй уровень фильтра — блок «Группы»');
  await d.show(subgroupBlock);
  await d.waitVoice();
  await d.click(popover.getByRole('button', { name: 'Применить' }));

  await expect(page.getByRole('button', { name: new RegExp(TEAM_WITH_GROUPS) })).toBeVisible({ timeout: 15_000 });
  await expect(kpiFactTile).toBeVisible({ timeout: 15_000 });
  await d.caption('Дашборд сразу пересчитался под другую команду');
  await d.show(kpiFactTile);
  await d.waitVoice();

  // Вернуться к своей команде.
  await d.click(page.locator('[data-tour="header-team"] button'), 'Вернёмся к своей команде');
  popover = page.locator('.ant-popover:visible');
  await d.click(popover.getByRole('button', { name: 'Сбросить' }));
  await d.type(popover.getByPlaceholder('Поиск команды'), 'Альфа');
  await d.click(popover.locator('[data-testid="team-filter-option"]', { hasText: TEAM }));
  await d.click(popover.getByRole('button', { name: 'Применить' }));
  await expect(page.getByRole('button', { name: new RegExp(TEAM) })).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(1100, 140);

  // Период: год, квартал, месяц.
  const periodSelects = page.locator('[data-tour="header-period"] .ant-select');
  await d.click(periodSelects.nth(1), 'Период — год, квартал, месяц — общий для всех разделов');
  await d.waitVoice();
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Q2 \(/ }));
  await expect(kpiFactTile).toBeVisible({ timeout: 15_000 });
  await d.caption('Смените квартал — цифры пересчитаются');
  await d.show(kpiFactTile);
  await d.pause(600);
  await d.point(periodSelects.nth(2));
  await page.mouse.move(1100, 140);
  await d.pause(300);

  // Справка раздела.
  const helpButton = page.locator('[data-tour="header-help"] button');
  const unreadDot = page.locator('[data-tour="header-help"] .ant-badge-dot');
  await d.click(helpButton, 'Кнопка со знаком вопроса открывает справку раздела');
  let drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await d.waitVoice();
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  if (await unreadDot.count()) {
    await d.caption('Красная точка на кнопке — в справке есть новости');
    await d.show(page.locator('[data-tour="header-help"]'));
    await d.pause(300);
  }

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'У каждого раздела своя справка');
  await d.click(helpButton);
  drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  const videoCard = drawer.getByRole('button', { name: /Смотреть видео/ }).first();
  await expect(videoCard).toBeVisible();
  await d.caption('В справке бывают короткие ролики');
  await d.show(videoCard);
  await d.waitVoice();
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  await d.click(page.locator('.side-item', { hasText: 'Дашборд' }));

  // Первые шаги.
  await d.click(page.locator('[data-tour="header-onboarding"]'), 'Кнопка «Первые шаги» — чек-лист настройки команды');
  drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await d.show(drawer.getByText('Настройка команды', { exact: true }));
  await d.pause(500);
  const introHeading = drawer.getByText('Знакомство с сервисом', { exact: true });
  await introHeading.scrollIntoViewIfNeeded();
  await d.caption('Ниже — знакомство с самим сервисом');
  await d.show(introHeading);
  await d.waitVoice();
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();

  // Тема оформления.
  const themeSelect = page.locator('.topbar .ant-select', { hasText: 'Aurora' });
  await d.click(themeSelect, 'Тему оформления можно сменить');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Aurora светлая' }));
  await d.pause(700);
  await d.click(themeSelect);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Aurora тёмная' }));
  await d.pause(500);

  await d.show(page.locator('[data-tour="dash-projects"]'));
  await d.caption('Готово', 2200);
  await d.save('start-header');
});
