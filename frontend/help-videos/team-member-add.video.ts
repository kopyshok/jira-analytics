// Ролик «Как добавить сотрудника в команду»: Ресурсы → вкладка «Команда» →
// «Добавить сотрудника» → найти человека → добавить → выбрать команду и роль в строке →
// карточка сотрудника — «В команде с…».
//
// Поиск людей в Jira (`GET /jira/users/search`) и список команд для селектора
// (`GET /sync/jira-teams`) в этой среде ходят в живую Jira — на съёмке credentials
// намеренно пустые (playwright.videos.config.ts), чтобы ролики не дёргали сеть. Оба
// запроса подменяются через page.route() прямо здесь, без правок director.ts/бэкенда:
// добавление сотрудника (POST /employees/from-jira) — обычный запрос к своей БД,
// в подмене не нуждается.
import { expect, test } from '@playwright/test';
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
  await d.type(modal.locator('input'), SEARCH_LETTERS, 'Найдите человека по имени');

  const option = page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: FAKE_USER.display_name });
  await expect(option).toBeVisible();
  await d.click(option, 'Выберите нужного из списка');
  await expect(modal).toBeHidden();

  // Новый сотрудник ещё без команды — под фильтром «Команда Альфа» в шапке его не видно.
  // Сначала сужаем список до одного человека (фильтр по сотруднику — обычный React-стейт,
  // применяется мгновенно), и только потом снимаем фильтр команды: так браузер ни разу
  // не рисует полный список компании (сотни сотрудников) ради одной новой строки.
  const empFilter = page.locator('[data-tour="capacity-toolbar"] .ant-select').first();
  await d.click(empFilter, 'Найдите его по имени в фильтре сотрудников');
  await empFilter.locator('input').pressSequentially(SEARCH_LETTERS, { delay: 90 });
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: FAKE_USER.display_name }));
  await page.keyboard.press('Escape');

  await d.click(page.getByRole('button', { name: /Команда Альфа/ }), 'И уберите фильтр команды — он в неё ещё не входит');
  await d.click(page.getByRole('button', { name: 'Сбросить' }));
  await d.click(page.getByRole('button', { name: 'Применить' }));

  const row = table.locator('tbody tr.capacity-emp-row', { hasText: FAKE_USER.display_name });
  await expect(row).toBeVisible({ timeout: 20_000 });
  await d.caption('Вот он — выбирайте команду и роль в строке');
  await d.show(row);
  await d.pause(400);

  const teamSelect = row.locator('[data-tour="capacity-teams-select"]');
  await d.click(teamSelect, 'Добавьте его в команду');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: TEAM }));
  await page.keyboard.press('Escape');
  await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);

  const roleSelect = row.locator('[data-tour="capacity-role"]');
  await d.click(roleSelect, 'Укажите его роль');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option').first());
  await expect(page.locator('.ant-select-dropdown:visible')).toHaveCount(0);
  await page.mouse.move(200, 120);
  await d.show(row);
  await d.pause(900);

  await d.caption('Готово', 2200);
  await d.save('team-member-add');
});
