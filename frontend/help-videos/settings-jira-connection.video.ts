// Ролик «Как подключить Jira, проекты и поля»: Настройки (демо-администратор) → «Подключение к Jira»
// (адрес, e-mail, токен, «Проверить подключение») → «Проекты в scope» («Загрузить из Jira», переключатели,
// «Сохранить») → «Поля Jira» (список полей для роли, «Альтернатива»/«Слагаемое», «Длительности»).
// Съёмочный стенд не ходит в Jira, поэтому ответы Jira подменяются в браузере (page.route), а записи
// настроек перехватываются и в базу не попадают: реальных адресов и токенов нет, база не меняется.
import { expect, test } from '@playwright/test';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Альфа';

const FIELDS = [
  ['customfield_10100', 'Продуктовая команда'],
  ['customfield_10101', 'Участвующие команды'],
  ['customfield_10102', 'Цели'],
  ['customfield_10210', 'Оценка разработки, ч (серверная часть)'],
  ['customfield_10211', 'Оценка разработки, ч (интерфейс)'],
  ['customfield_10212', 'Оценка анализа, ч'],
  ['customfield_10213', 'Оценка тестирования, ч'],
  ['customfield_10220', 'Длительность анализа, дн'],
  ['customfield_10221', 'Длительность разработки, дн'],
  ['customfield_10222', 'Длительность тестирования, дн'],
  ['customfield_10300', 'Влияние'],
  ['customfield_10301', 'Риск'],
  ['customfield_10400', 'Разработчик'],
  ['customfield_10401', 'Спринт'],
].map(([id, name]) => ({ id, name, custom: true }));

/** Что «уже сохранено» в настройках полей: чтобы в кадре не было пустых списков. */
const SAVED: Record<string, string> = {
  jira_team_field_id: 'customfield_10100',
  jira_participating_teams_field_id: 'customfield_10101',
  jira_goals_field_id: 'customfield_10102',
  jira_planned_dev_hours_field_id: 'customfield_10210',
  jira_planned_analyst_hours_field_id: 'customfield_10212',
  jira_planned_qa_hours_field_id: 'customfield_10213',
  jira_duration_analyst_field_id: 'customfield_10220',
  jira_duration_dev_field_id: 'customfield_10221',
  jira_duration_qa_field_id: 'customfield_10222',
  jira_impact_field_id: 'customfield_10300',
  jira_risk_field_id: 'customfield_10301',
  jira_developer_field_id: 'customfield_10400',
  jira_sprint_field_id: 'customfield_10401',
};

const json = (body: unknown) => ({ contentType: 'application/json', body: JSON.stringify(body) });

test('settings-jira-connection', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const scope = (await (await page.request.get(`${api}/scope/projects`)).json()) as { jira_project_key: string }[];
  const realKeys = scope.map((s) => s.jira_project_key).slice(0, 4);
  const projects = [
    ...realKeys.map((key, i) => ({ id: `r${i}`, key, name: `Проект ${key}`, project_type: 'software' })),
    { id: 'f1', key: 'PORTAL', name: 'Клиентский портал', project_type: 'software' },
    { id: 'f2', key: 'MOBILE', name: 'Мобильное приложение', project_type: 'software' },
    { id: 'f3', key: 'DATA', name: 'Хранилище данных', project_type: 'software' },
    { id: 'f4', key: 'SUPPORT', name: 'Поддержка пользователей', project_type: 'service_desk' },
  ];

  // Ответы Jira и запись настроек — подмена в браузере.
  await page.route('**/api/v1/settings/jira/test', (route) =>
    route.fulfill(json({ connected: true, user_name: 'Сервисная учётная запись', user_email: 'integrator@example.com', error: null })));
  await page.route('**/api/v1/settings/jira', (route) => {
    if (route.request().method() === 'GET') return route.fulfill(json({ base_url: 'https://jira.example.com', email: null, has_token: false }));
    return route.fulfill(json({ base_url: 'https://jira.example.com', email: 'integrator@example.com', has_token: true }));
  });
  await page.route('**/api/v1/sync/jira-projects**', (route) => route.fulfill(json(projects.map((p) => ({ ...p, in_scope: realKeys.includes(p.key) })))));
  await page.route('**/api/v1/sync/jira-teams', (route) => route.fulfill(json([TEAM, 'Команда Бета', 'Команда Гамма'])));
  await page.route('**/api/v1/sync/jira-fields', (route) => route.fulfill(json(FIELDS)));
  await page.route('**/api/v1/scope/projects/batch', (route) => {
    const body = route.request().postDataJSON() as { add: string[]; remove: string[] };
    return route.fulfill(json({ added: body.add.length, removed: body.remove.length }));
  });
  await page.route('**/api/v1/settings/generic**', (route) => {
    const req = route.request();
    if (req.method() !== 'GET') return route.fulfill(json({ key: 'x', ok: true }));
    const key = decodeURIComponent(new URL(req.url()).pathname.split('/').pop() ?? '');
    if (key in SAVED) return route.fulfill(json({ key, value: SAVED[key] }));
    return route.continue();
  });

  const menu = (text: string) => page.locator('.ant-menu-item', { hasText: text });
  const toTop = () => page.evaluate(() => window.scrollTo({ top: 0 }));
  const center = (loc: import('@playwright/test').Locator) => loc.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  const option = (text: string) => page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: text });

  await d.open('/settings#connection', 'Как подключить Jira, проекты и поля');
  const card = page.locator('.ant-card', { hasText: 'Подключение к Jira' }).first();
  await expect(card.getByRole('button', { name: /Проверить подключение/ })).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await toTop();
  const url = card.locator('input[name="jira-base-url"]');
  await url.fill('');
  await d.type(url, 'https://jira.example.com', 'Укажите адрес вашей Jira');
  await d.type(card.locator('input[name="jira-email"]'), 'integrator@example.com', 'Затем почту сервисной учётной записи');
  await d.type(card.locator('input[name="jira-api-token"]'), 'demo-token-123', 'И её токен — он виден только точками');
  await d.click(card.getByRole('button', { name: /Проверить подключение/ }), 'Проверьте подключение до первой синхронизации');
  await expect(page.locator('.ant-message').getByText(/Подключение успешно/)).toBeVisible();
  await d.show(page.locator('.ant-message').getByText(/Подключение успешно/));
  await d.waitVoice();
  await page.mouse.move(60, 120);

  await d.click(menu('Проекты в scope'), 'Дальше выберите проекты, которые загружать из Jira');
  await toTop();
  const scopeCard = page.locator('.ant-card', { hasText: 'Текущий scope' }).first();
  await expect(scopeCard).toBeVisible();
  await d.caption('Сверху — проекты, которые загружаются сейчас');
  await d.show(scopeCard);
  await d.click(page.getByRole('button', { name: /Загрузить из Jira/ }), 'Список проектов запрашивают кнопкой «Загрузить из Jira»');
  const table = page.locator('.ant-card', { hasText: 'Разделы задач' }).last();
  await expect(table.locator('.ant-table-row').first()).toBeVisible();
  await d.show(table.locator('.ant-table'));
  const rowOf = (key: string) => table.locator('.ant-table-row', { hasText: key });
  await d.click(rowOf('PORTAL').locator('.ant-switch'), 'Переключателем включите нужный проект');
  await d.click(rowOf('MOBILE').locator('.ant-switch'));
  await expect(page.getByText(/Изменений: 2/)).toBeVisible();
  await d.caption('Изменения копятся, пока вы не нажмёте «Сохранить»');
  await d.show(page.getByText(/Изменений: 2/));
  await d.click(page.locator('.ant-card-extra').getByRole('button', { name: /Сохранить/ }));
  await expect(page.locator('.ant-notification').getByText('Scope обновлён')).toBeVisible();
  await page.mouse.move(60, 120);
  await d.waitVoice();

  await d.click(menu('Поля Jira'), 'Наконец, сопоставьте поля Jira с данными сервиса');
  await toTop();
  const fields = page.locator('.ant-card', { hasText: 'Кастомные поля Jira' }).first();
  await expect(fields).toBeVisible();
  await expect(fields.getByText('Продуктовая команда').first()).toBeVisible();
  await d.show(fields.locator('.ant-collapse').first());
  const devRow = fields.locator('.ant-form-item', { hasText: 'Разработка (часы)' });
  await center(devRow);
  await d.click(devRow.getByRole('button', { name: /Добавить поле/ }), 'Для оценки в часах можно указать несколько полей');
  await d.click(devRow.locator('.ant-select').nth(1));
  await d.click(option('интерфейс'));
  await d.click(devRow.locator('.ant-segmented-item', { hasText: 'Слагаемое' }).last(), 'Слагаемое складывается с первым полем, альтернатива — отдельная оценка');
  await d.show(devRow);
  await d.waitVoice();

  const durations = fields.locator('.ant-collapse-header', { hasText: 'Длительности' });
  await center(durations);
  await d.click(durations, 'В «Длительностях» — поля для ресурсного планирования');
  await d.show(fields.locator('.ant-collapse-item', { hasText: 'Длительности' }));
  await d.waitVoice();
  await toTop();
  await d.click(fields.getByRole('button', { name: /Сохранить/ }), 'Сохраните — следующая синхронизация возьмёт поля отсюда');
  await expect(page.locator('.ant-message').getByText('Сохранено')).toBeVisible();
  await page.mouse.move(60, 120);
  await d.pause(600);

  await d.caption('Готово', 2200);
  await d.save('settings-jira-connection');
});
