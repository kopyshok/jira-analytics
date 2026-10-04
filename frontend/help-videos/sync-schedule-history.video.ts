// Ролик «Как настроить автосинхронизацию»: Синхронизация (режимы, запуск не жмём) →
// «Расписание» → «Добавить» (будни в 7:00, режим «Быстрый», превью «Следующие запуски»)
// → правило в таблице выключенным → «История запусков» (подсаженные записи, этапы).
// Синхронизацию не запускаем. Правило и подсаженная история убираются в afterAll.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const RULE_NAME = 'Утреннее обновление';
const SEED_TAG = 'video-seed-';

function runDbPath(): string {
  const port = process.env.VIDEOS_BACKEND_PORT ?? '8012';
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

/** Время в формате базы (UTC), «минут назад». */
function ago(minutes: number): string {
  return new Date(Date.now() - minutes * 60_000).toISOString().replace('T', ' ').replace('Z', '000');
}

const stage = (name: string, status: string, counts: Record<string, number>, startMin: number, endMin: number, error?: string) => ({
  stage: name, status, counts, error: error ?? null, started: ago(startMin), finished: ago(endMin),
});

function seedHistory() {
  const db = new DatabaseSync(runDbPath());
  try {
    db.exec(`DELETE FROM sync_run WHERE id LIKE '${SEED_TAG}%'`);
    const ins = db.prepare(
      `INSERT INTO sync_run (id, started_at, finished_at, status, "trigger", mode, team, stages_json, error_text, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    );
    const rows = [
      ['a', 1500, 1496, 'ok', 'scheduled', 'normal', null, [
        stage('calendar', 'ok', { days: 366 }, 1500, 1499), stage('projects', 'ok', { projects: 14 }, 1499, 1498),
        stage('issues', 'ok', { updated: 182, created: 9 }, 1498, 1497), stage('worklogs', 'ok', { added: 241, changed: 17 }, 1497, 1496),
      ], null],
      ['b', 780, 779, 'ok', 'scheduled', 'quick', null, [
        stage('worklogs', 'ok', { added: 58, changed: 4 }, 780, 779),
      ], null],
      ['c', 330, 327, 'failed', 'manual', 'normal', null, [
        stage('calendar', 'ok', { days: 366 }, 330, 329), stage('projects', 'ok', { projects: 14 }, 329, 328),
        stage('issues', 'failed', {}, 328, 327, 'Jira не ответила вовремя'),
      ], 'Jira не ответила вовремя'],
      ['d', 120, 118, 'cancelled', 'manual', 'team', TEAM, [
        stage('worklogs', 'cancelled', { added: 12 }, 120, 118),
      ], null],
    ] as const;
    for (const [k, start, end, status, trigger, mode, team, stages, err] of rows) {
      ins.run(`${SEED_TAG}${k}`, ago(start), ago(end), status, trigger, mode, team, JSON.stringify(stages), err, ago(start), ago(end));
    }
  } finally {
    db.close();
  }
}

function cleanDb() {
  const db = new DatabaseSync(runDbPath());
  try {
    db.exec(`DELETE FROM sync_run WHERE id LIKE '${SEED_TAG}%'`);
    db.prepare('DELETE FROM sync_schedule WHERE name = ?').run(RULE_NAME);
  } finally {
    db.close();
  }
}

test.beforeAll(async () => {
  cleanDb();
  seedHistory();
});

test.afterAll(async () => {
  cleanDb();
});

test('sync-schedule-history', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  await d.open('/sync', 'Как настроить автосинхронизацию');
  await expect(page.getByText('Запуск синхронизации')).toBeVisible();
  await expect(page.locator('.ant-table-row', { hasText: 'Прерван' })).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await d.click(page.locator('.side-item', { hasText: 'Синхронизация' }), 'Откройте раздел «Синхронизация»');
  const runner = page.locator('.ant-card', { hasText: 'Запуск синхронизации' }).first();
  await d.caption('Здесь данные из Jira попадают в сервис');
  await d.show(runner);

  const modeSelect = runner.locator('.ant-select').first();
  await d.click(modeSelect, 'Режим запуска выбирают в этом списке');
  await expect(page.locator('.ant-select-dropdown:visible')).toBeVisible();
  await d.caption('Быстрый берёт только часы, обычный ещё и задачи');
  await d.show(page.locator('.ant-select-dropdown:visible'));
  await d.caption('Полный перечитывает всё, а по команде обновляет одну команду');
  await d.pause(600);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await page.mouse.move(200, 120);

  await d.click(page.getByRole('tab', { name: 'Расписание' }), 'Чтобы не запускать вручную, откройте «Расписание»');
  await d.click(page.getByRole('button', { name: /Добавить/ }), 'Нажмите «Добавить»');
  const modal = page.locator('.ant-modal', { hasText: 'Новое расписание' });
  await expect(modal).toBeVisible();

  await d.type(modal.locator('#name'), RULE_NAME, 'Назовите правило');
  await d.click(modal.locator('#type'), 'Выберите тип расписания');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Будни' }));

  await d.click(modal.locator('#time'), 'Укажите время запуска');
  const panel = page.locator('.ant-picker-dropdown:visible');
  await panel.locator('.ant-picker-time-panel-column').first().locator('li', { hasText: /^07$/ }).click();
  await d.pause(500);
  await d.click(panel.locator('.ant-picker-ok button'));
  await expect(modal.locator('#time')).toHaveValue('07:00');

  await d.click(modal.locator('#mode'), 'Выберите режим «Быстрый»');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Быстрый' }));

  const preview = modal.locator('.ant-alert');
  await expect(preview).toContainText('Следующие запуски');
  await d.caption('Ниже видно, когда правило сработает в ближайшие дни');
  await d.show(preview);

  // Правило создаётся выключенным: в демо-стенде Jira нет.
  const enabled = modal.locator('#enabled');
  await d.click(enabled, 'Выключите переключатель — правило пока не должно работать');
  await expect(enabled).toHaveAttribute('aria-checked', 'false');
  await d.click(modal.getByRole('button', { name: 'Сохранить' }), 'Нажмите «Сохранить»');
  await expect(modal).toBeHidden();

  const row = page.locator('.ant-table-row', { hasText: RULE_NAME });
  await expect(row).toBeVisible();
  await page.mouse.move(200, 120);
  await d.caption('Правило появилось в таблице, переключатель выключен');
  await d.show(row);
  await d.pause(600);

  await d.waitVoice();
  await d.click(page.getByRole('tab', { name: 'Синхронизация' }), 'Результаты запусков смотрите на первой вкладке');
  const history = page.locator('.ant-card', { hasText: 'История запусков' }).first();
  await expect(history.locator('.ant-table-row').first()).toBeVisible();
  await d.caption('«История запусков» показывает время, режим, статус и источник');
  await d.show(history);

  const failed = history.locator('.ant-table-row', { hasText: 'Ошибка' });
  await d.click(failed.locator('.ant-table-row-expand-icon'), 'Раскройте строку, чтобы увидеть этапы запуска');
  await expect(history.locator('.ant-collapse').first()).toBeVisible();
  await d.show(history.locator('.ant-table-expanded-row'));
  await d.caption('Видно, на каком этапе сбой и что он сообщил');
  await d.pause(600);

  await d.caption('Готово', 2200);
  await d.save('sync-schedule-history');
});
