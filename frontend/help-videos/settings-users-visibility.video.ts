// Ролик «Как завести пользователя и скрыть лишние разделы»: «Настройки» → «Пользователи» —
// новый пользователь (роль «Руководитель», команда по умолчанию) → «Видимость разделов» —
// скрыть раздел → меню без раздела → видимость возвращена.
// От имени демо-администратора. В конце видимость возвращена, пользователь удалён из копии
// базы съёмки (в самом сервисе пользователя можно только выключить).
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Альфа';
const NEW_NAME = 'Новый сотрудник';
const NEW_EMAIL = 'new.employee@example.com';
const HIDE_LABEL = 'Проекты';

let originalHidden: string[] = [];

function runDbPath(backendUrl: string): string {
  const port = new URL(backendUrl).port;
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

/** Убрать созданного пользователя из копии базы съёмки. */
function dropUser(backendUrl: string): void {
  const db = new DatabaseSync(runDbPath(backendUrl));
  try {
    db.exec('PRAGMA busy_timeout = 10000');
    db.prepare('DELETE FROM users WHERE email = ?').run(NEW_EMAIL);
  } finally {
    db.close();
  }
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const backendUrl = String(testInfo.config.metadata.backendUrl);
  const api = `${backendUrl}/api/v1`;
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  dropUser(backendUrl);
  originalHidden = ((await (await request.get(`${api}/ui-config/hidden-sections`)).json()) as { keys: string[] }).keys;
  // Начинаем с меню, где раздел «Проекты» виден.
  await request.put(`${api}/ui-config/hidden-sections`, {
    data: { keys: originalHidden.filter((k) => k !== '/projects') },
  });
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const backendUrl = String(testInfo.config.metadata.backendUrl);
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  await request.put(`${backendUrl}/api/v1/ui-config/hidden-sections`, { data: { keys: originalHidden } });
  await request.dispose();
  dropUser(backendUrl);
});

test('settings-users-visibility', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/settings#users', 'Как завести пользователя и скрыть лишние разделы');
  const addUser = page.getByRole('button', { name: /Добавить пользователя/ });
  await expect(addUser).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const menuItem = (label: string) => page.locator('.ant-menu-item', { hasText: label });

  await d.caption('«Пользователи» — кто может входить в сервис');
  await d.show(menuItem('Пользователи'));
  await d.pause(1500);

  await d.click(addUser, 'Нажмите «Добавить пользователя»');
  const modal = page.locator('.ant-modal', { hasText: 'Новый пользователь' });
  await expect(modal).toBeVisible();
  await d.type(modal.locator('#display_name'), NEW_NAME, 'Имя сотрудника');
  await d.type(modal.locator('#email'), NEW_EMAIL, 'Почта — это его логин');
  await d.type(modal.locator('#password'), 'demo12345', 'Пароль — не короче восьми знаков');
  await d.click(modal.locator('.ant-form-item', { hasText: 'Роль' }).locator('.ant-select'), 'Роль — «Руководитель»');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Руководитель$/ }));
  await d.type(modal.locator('#default_team'), TEAM, 'Команда по умолчанию — её он увидит при входе');
  await d.click(modal.getByRole('button', { name: 'Создать' }), 'Создайте пользователя');
  await expect(modal).toBeHidden();
  await page.mouse.move(1300, 120);

  const newRow = page.locator('tr.ant-table-row', { hasText: NEW_NAME });
  if (!(await newRow.count())) await page.locator('.ant-pagination-item-2').click();
  await expect(newRow).toBeVisible({ timeout: 10_000 });
  await d.caption('Пользователь в списке: роль и команда на месте');
  await d.show(newRow);
  await d.pause(1800);

  // === Видимость разделов ===
  await d.waitVoice();
  await d.click(menuItem('Видимость разделов'), 'Теперь «Видимость разделов»');
  const checkbox = page.locator('label.ant-checkbox-wrapper', { hasText: `Скрыть «${HIDE_LABEL}»` });
  await expect(checkbox).toBeVisible({ timeout: 15_000 });
  const sideItem = page.locator('.side-item', { hasText: new RegExp(`^${HIDE_LABEL}$`) });
  await expect(sideItem).toBeVisible();
  await d.caption('Настройка общая — касается всех пользователей');
  await d.show(sideItem);
  await d.pause(2000);

  await d.click(checkbox, `Отметьте раздел «${HIDE_LABEL}»`);
  await d.click(page.getByRole('button', { name: 'Сохранить' }), 'И сохраните');
  await expect(sideItem).toHaveCount(0, { timeout: 10_000 });
  await page.mouse.move(1300, 120);
  await d.caption('Из бокового меню раздел исчез. Сами данные остались');
  await d.show(page.locator('.side-item').first(), page.locator('.side-item').last());
  await d.pause(2500);

  await d.click(checkbox, 'Чтобы вернуть раздел, снимите галочку');
  await d.click(page.getByRole('button', { name: 'Сохранить' }), 'И сохраните');
  await expect(sideItem).toBeVisible({ timeout: 10_000 });
  await page.mouse.move(1300, 120);
  await d.caption('Раздел снова в меню');
  await d.show(sideItem);
  await d.pause(1800);

  await d.caption('Готово', 2200);
  await d.save('settings-users-visibility');
});
