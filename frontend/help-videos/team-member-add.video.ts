// Ролик «Как добавить сотрудника в команду»: Ресурсы → вкладка «Команда» →
// «Добавить сотрудника» → найти человека → команда и роль в строке → карточка
// сотрудника — дата «В команде с…». → Сценарии: новый человек виден в ресурсе
// по ролям и «По сотрудникам».
//
// Поиск людей в Jira (`GET /jira/users/search`) и список команд для селектора
// (`GET /sync/jira-teams`) в этой среде ходят в живую Jira — на съёмке credentials
// намеренно пустые (playwright.videos.config.ts), чтобы ролики не дёргали сеть. Оба
// запроса подменяются через page.route() прямо здесь, без правок director.ts/бэкенда:
// добавление сотрудника (POST /employees/from-jira) — обычный запрос к своей БД,
// в подмене не нуждается.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';

const FAKE_USER = {
  jira_account_id: 'video-mock-artem-raevskiy',
  display_name: 'Артём Раевский',
  email: 'a.raevskiy@example.com',
  is_active: true,
  avatar_url: null,
};
const SEARCH_LETTERS = 'Раев';
const TEAM = 'Команда Альфа';

test('team-member-add', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  await page.route('**/api/v1/jira/users/search**', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify([FAKE_USER]) }));
  await page.route('**/api/v1/sync/jira-teams', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify([TEAM, 'Команда Бета', 'Команда Гамма']) }));

  await d.open('/capacity', 'Как добавить сотрудника в команду');
  const table = page.locator('[data-tour="capacity-team-table"]');
  await expect(table.locator('tbody tr.capacity-emp-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');

  await d.click(page.locator('[data-tour="capacity-add-employee"]'), 'Нажмите «Добавить сотрудника»');
  const modal = page.locator('.ant-modal', { hasText: 'Добавить сотрудника из Jira' });
  await expect(modal).toBeVisible();
  const [addResp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/employees/from-jira') && r.request().method() === 'POST'),
    (async () => {
      await d.type(modal.locator('input'), SEARCH_LETTERS, 'Найдите человека по имени');
      const option = page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: FAKE_USER.display_name });
      await expect(option).toBeVisible();
      await d.click(option, 'Выберите нужного из списка');
    })(),
  ]);
  const newEmployee: { id: string } = await addResp.json();
  await expect(modal).toBeHidden();

  // Новый сотрудник ещё без команды — под фильтром «Команда Альфа» в шапке его не видно.
  // Сначала сужаем список до одного человека (фильтр по сотруднику — обычный React-стейт,
  // применяется мгновенно), и только потом снимаем фильтр команды: так браузер ни разу
  // не рисует полный список компании (сотни сотрудников) ради одной новой строки.
  const empFilter = page.locator('[data-tour="capacity-toolbar"] .ant-select').first();
  await d.click(empFilter, 'Найдите нового сотрудника в фильтре по имени');
  await empFilter.locator('input').pressSequentially(SEARCH_LETTERS, { delay: 90 });
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: FAKE_USER.display_name }));
  await page.keyboard.press('Escape');

  await d.click(page.getByRole('button', { name: /Команда Альфа/ }), 'И уберите фильтр команды — новичок в неё ещё не входит');
  await d.waitVoice();
  await d.click(page.getByRole('button', { name: 'Сбросить' }));
  await d.click(page.getByRole('button', { name: 'Применить' }));

  const row = table.locator('tbody tr.capacity-emp-row', { hasText: FAKE_USER.display_name });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await d.caption('Новый сотрудник в списке — команда и роль задаются в строке');
  await d.show(row);
  await d.pause(400);

  const teamSelect = row.locator('[data-tour="capacity-teams-select"]');
  await expect(teamSelect).toBeVisible();
  await d.click(teamSelect, 'Добавьте сотрудника в команду');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: TEAM }));
  await page.keyboard.press('Escape');
  await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);

  const roleSelect = row.locator('[data-tour="capacity-role"]');
  // Строка перерисовывается после сохранения команды (особенно если человек
  // уже существовал деактивированным) — ждём стабильного состояния перед кликом.
  await expect(roleSelect).toBeVisible();
  await d.click(roleSelect, 'Укажите роль');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option').first());
  await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
  await page.mouse.move(200, 120);

  // Карточка сотрудника: он активен и в команде — но с какого числа?
  await d.click(row.getByText(FAKE_USER.display_name, { exact: true }), 'Откройте карточку сотрудника');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(TEAM).first()).toBeVisible();
  await d.caption('Переключатель «Активен» — сотрудник учитывается в расчётах');
  await d.show(drawer.getByRole('switch'));
  await d.pause(900);

  const joinedInput = drawer.locator('input[placeholder="В команде с…"]');
  await d.click(joinedInput, 'Отметьте дату входа, если не с начала квартала');
  const dropdown = page.locator('.ant-picker-dropdown:visible');
  // Середина текущего квартала, 15-е число: сценарий этого квартала есть всегда.
  const now = dayjs();
  const joinDate = dayjs(new Date(now.year(), Math.floor(now.month() / 3) * 3 + 1, 15));
  for (let i = 0; i < 12 && !(await dropdown.locator(
    `td.ant-picker-cell-in-view[title="${joinDate.format('YYYY-MM-DD')}"]`).count()); i++) {
    await dropdown.locator('.ant-picker-header-next-btn').click();
  }
  await d.click(dropdown.locator(`td.ant-picker-cell-in-view[title="${joinDate.format('YYYY-MM-DD')}"]`));
  await expect(page.getByText('Сохранено')).toBeVisible();
  await d.caption('Именно с этой даты сотрудник войдёт в ресурс команды');
  await d.show(joinedInput);
  await d.pause(1200);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();

  // Фильтр команды в шапке был снят ради поиска нового человека — возвращаем,
  // иначе список сценариев ниже распухнет до всех команд компании.
  await d.click(page.getByRole('button', { name: /Все команды/ }), 'Верните фильтр на «Команда Альфа»');
  await d.click(page.locator('[data-testid="team-filter-option"]', { hasText: TEAM }));
  await d.click(page.getByRole('button', { name: 'Применить' }));
  await expect(page.getByRole('button', { name: new RegExp(TEAM) })).toBeVisible();

  // Сценарии: ресурс по ролям и «По сотрудникам» выросли за счёт нового человека.
  const quarter = Math.floor(joinDate.month() / 3) + 1;
  const year = joinDate.year();
  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'Загляните в сценарий этого квартала');
  const scenarioSelect = page.locator('[data-tour="planning-scenario-select"]');
  await d.click(scenarioSelect, 'Выберите сценарий команды');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', {
    hasText: new RegExp(`Q${quarter} ${year}`),
  }));

  const panel = page.locator('[data-tour="planning-capacity-panel"]');
  await expect(panel).toBeVisible();
  const newRow = panel.getByText(FAKE_USER.display_name);
  await newRow.scrollIntoViewIfNeeded();
  await expect(newRow).toBeVisible({ timeout: 15_000 });
  await d.caption('Новый человек уже в ресурсе по ролям и по сотрудникам');
  await d.show(newRow);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('team-member-add');

  // Уборка: сотрудник фиктивный (mock-поиск Jira), убираем его из команды и
  // выключаем, чтобы не путался в остальных роликах.
  await page.request.put(`${api}/employees/${newEmployee.id}/teams`, { data: { teams: [], primary: null } });
  await page.request.patch(`${api}/employees/${newEmployee.id}`, { data: { role: null, is_active: false } });
});
