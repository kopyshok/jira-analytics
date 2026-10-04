// Ролик «Как понять, почему в ведомости пусто»: KPI → строка итогов →
// «разобрать» («Почему не хватает данных») → «кто не попал» («Роль не
// заполнена») → «Последние месяцы» и стрелки периода → свёртка команды.
// В копию базы подсажена пустая роль у одного сотрудника команды (в afterAll
// возвращается); пустая клетка «Cycle Time» есть сама: на текущий квартал
// не задан норматив.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
/** Сотрудник Альфы с ролью «Консультант» — в профили оценки не входит. */
const NO_ROLE_NAME = 'Гуляев Пётр';

let dbPath = '';
let savedRole: string | null = null;
let seeded = false;

function withDb<T>(fn: (db: DatabaseSync) => T): T | undefined {
  try {
    const db = new DatabaseSync(dbPath);
    try {
      return fn(db);
    } finally {
      db.close();
    }
  } catch {
    // Файл занят сервером — уборка не должна ронять ролик.
    return undefined;
  }
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const backendUrl = String(testInfo.config.metadata.backendUrl);
  const api = `${backendUrl}/api/v1`;
  dbPath = fileURLToPath(new URL(`../../data/demo_run_${new URL(backendUrl).port}.db`, import.meta.url));
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  await request.dispose();

  const row = withDb((db) => db.prepare('SELECT role FROM employees WHERE display_name = ?').get(NO_ROLE_NAME) as
    { role: string | null } | undefined);
  expect(row, `нет сотрудника «${NO_ROLE_NAME}» в демо-базе`).toBeTruthy();
  savedRole = row!.role;
  withDb((db) => db.prepare('UPDATE employees SET role = NULL WHERE display_name = ?').run(NO_ROLE_NAME));
  seeded = true;
});

test.afterAll(() => {
  if (seeded) {
    withDb((db) => db.prepare('UPDATE employees SET role = ? WHERE display_name = ?').run(savedRole, NO_ROLE_NAME));
  }
});

test('kpi-gaps', async ({ page }) => {
  const now = new Date();
  const d = new Director(page);
  await d.install();
  await d.open(
    `/kpi?kpiYear=${now.getFullYear()}&kpiMonth=${now.getMonth() + 1}&kpiMonths=3`,
    'Как понять, почему в ведомости пусто',
  );

  const ledgerCard = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Ведомость' }) });
  await expect(ledgerCard).toBeVisible({ timeout: 20_000 });
  const summary = page.locator('span', { hasText: /^Средний КЭ/ }).first().locator('xpath=ancestor::div[1]');
  await expect(summary).toBeVisible();
  await d.pause(1200);
  await d.poster();
  await d.pause(1500);

  const drawer = page.getByRole('dialog');
  const closeDrawer = async () => {
    await d.waitVoice();
    await page.locator('.ant-drawer-close').click();
    await expect(drawer).toBeHidden();
    await page.mouse.move(700, 120);
    await d.pause(400);
  };

  await d.caption('Строка итогов — сколько клеток пустых и кого не оценили');
  await d.show(summary);
  await d.pause(600);

  await d.click(page.getByRole('button', { name: 'разобрать' }), 'Нажмите «разобрать» — откроется «Почему не хватает данных»');
  await expect(drawer).toBeVisible();
  await d.show(drawer.locator('.ant-table'));
  await d.pause(500);
  await d.caption('По каждой метрике сказано, у кого пусто и почему');
  await d.pause(900);
  await d.click(drawer.locator('.ant-table-row-expand-icon').first(), 'Плюс раскрывает имена тех, у кого клетка пустая');
  await d.pause(800);
  await closeDrawer();

  await d.click(page.getByRole('button', { name: 'кто не попал' }), 'Нажмите «кто не попал» — список тех, кого в ведомости нет');
  await expect(drawer).toBeVisible();
  await d.show(drawer.locator('.ant-table'));
  await d.pause(500);
  await d.caption('«Роль не заполнена» — роль вносят в карточке сотрудника');
  await d.show(drawer.locator('.ant-tag-warning').first());
  await d.pause(700);
  await closeDrawer();

  await d.click(page.locator('.ant-segmented-item', { hasText: 'Последние месяцы' }), 'Режим «Последние месяцы» считает до нынешнего месяца');
  await d.pause(600);
  await d.click(page.getByRole('button', { name: 'Предыдущий период' }), 'Стрелкой вернитесь на период назад');
  await expect(ledgerCard).toBeVisible();
  await page.mouse.move(700, 120);
  await d.caption('В другом периоде пустоты другие — так видно, когда данные пропали');
  await d.show(ledgerCard);
  await d.pause(700);
  await d.caption('Чаще всего пусто, если в Jira не заполнено поле или давно не было синхронизации');
  await d.pause(600);

  await d.caption('Фильтр «Продуктовое направление» оставляет одно направление');
  await d.show(page.locator('.ant-select', { hasText: 'Продуктовое направление' }));
  await d.pause(600);

  const teamRow = ledgerCard.locator('tr', { hasText: TEAM }).first();
  await d.click(teamRow, 'Клик по строке команды сворачивает сотрудников');
  await d.pause(700);
  await d.click(teamRow, 'И разворачивает обратно');
  await page.mouse.move(700, 120);
  await d.pause(500);

  await d.show(ledgerCard);
  await d.caption('Готово', 2200);
  await d.pause(500);
  await d.save('kpi-gaps');
});
