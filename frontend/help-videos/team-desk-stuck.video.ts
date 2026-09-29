// Ролик «Как разобрать зависшие задачи»: Стол тимлида → «Светофор» → лента
// «Требует внимания» → «Зависла» → отметка «Просмотрено» с комментарием →
// задача уходит из списка; «показывать просмотренные» возвращает её на экран
// приглушённым значком, «Вернуть в проблемные» снимает отметку обратно.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const FLAG = 'stale';
const FLAG_LABEL = 'Зависла';
const FLAG_ICON = '⏳';

interface DeskIssue {
  id: string;
  key: string;
  status_group: string;
  is_subtask: boolean;
  flags: string[];
  signatures: Record<string, string>;
}
interface Overview {
  issues: DeskIssue[];
  flag_counts: Partial<Record<string, number>>;
}

let issueId = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  // Шапка и рабочее место раздела — заранее: ролик не должен начинаться с
  // пустого экрана «Выберите команды» или с чужих настроек прошлого ролика.
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/team-desk-filter`, {
    data: {
      teams: [TEAM], mode: 'open', show_reviewed: false, show_done_subtasks: true,
      group_by_developer: true, hidden_columns: ['sprint', 'release', 'daily_rate', 'scale', 'days'],
    },
  })).ok()).toBeTruthy();

  const overviewRes = await request.get(`${api}/team-desk/overview`, {
    params: { teams: TEAM, only_open: 'true', show_reviewed: 'false', show_done_subtasks: 'true' },
  });
  expect(overviewRes.ok()).toBeTruthy();
  const overview = (await overviewRes.json()) as Overview;
  expect(overview.flag_counts[FLAG] ?? 0, `нет задач с замечанием «${FLAG_LABEL}»`).toBeGreaterThan(0);

  // Самостоятельная задача «в работе» — статус читается на экране без
  // служебных пояснений; сортировка по ключу — один и тот же выбор при
  // повторном прогоне на той же копии базы.
  const candidates = overview.issues
    .filter((i) => i.flags.includes(FLAG) && !i.is_subtask)
    .sort((a, b) => a.key.localeCompare(b.key));
  const target = candidates.find((i) => i.status_group === 'dev') ?? candidates[0];
  expect(target, `нет подходящей задачи с замечанием «${FLAG_LABEL}»`).toBeTruthy();
  issueId = target!.id;

  // На случай, если прошлый прогон на этой же копии базы оставил отметку —
  // ролик должен проходить дважды подряд без ручной чистки.
  await request.delete(`${api}/team-desk/issues/${issueId}/mark`, { params: { flag: FLAG } }).catch(() => undefined);
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (issueId) {
    await request.delete(`${api}/team-desk/issues/${issueId}/mark`, { params: { flag: FLAG } }).catch(() => undefined);
  }
  await request.dispose();
});

test('team-desk-stuck', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/team-desk', 'Как разобрать зависшие задачи');

  const filters = page.locator('[data-tour="desk-filters"]');
  const issuesBlock = page.locator('[data-tour="desk-issues"]');
  await expect(issuesBlock).toBeVisible({ timeout: 20_000 });
  await d.pause(1100);
  await d.poster();
  await d.pause(1700);

  await d.caption('Команда уже выбрана в шапке — «Команда Альфа»');
  await d.show(filters.locator('.ant-select').first());
  await d.pause(1400);

  await d.caption('Раскладка «Светофор» — плитка на каждого разработчика');
  await d.show(page.locator('[data-tour="desk-tabs"]'));
  await d.pause(1400);

  const flagBar = page.locator('[data-tour="desk-flags"] .ant-tag', { hasText: new RegExp(`${FLAG_LABEL} ·`) });
  await expect(flagBar).toBeVisible();
  const countBefore = Number((await flagBar.innerText()).replace(/\D+/g, ''));

  await d.caption('Полоса «Требует внимания» — тут задачи с замечанием');
  await d.show(flagBar);
  await d.pause(1300);

  await d.click(flagBar, `Отфильтруйте по замечанию «${FLAG_LABEL}»`);
  await d.pause(1200);

  const row = issuesBlock.locator(`tr[data-row-key="${issueId}"]`);
  await expect(row).toBeVisible();
  await d.show(row);
  await d.pause(1400);

  // Значок замечания — по иконке: в строке есть и другой тэг (статус), а
  // иконка признака встречается только в колонке «Замечания».
  const flagChip = row.locator('.ant-tag', { hasText: FLAG_ICON });
  await d.click(flagChip, 'Нажмите на значок замечания у задачи');
  await d.click(page.locator('.ant-dropdown-menu-item', { hasText: 'Просмотрено' }), 'Выберите «Просмотрено»');

  const modal = page.locator('.ant-modal', { hasText: 'Просмотрено' });
  await expect(modal).toBeVisible();
  await d.pause(400);
  await d.type(modal.locator('textarea'), 'Уточнили у автора, ждём ответ', 'Можно оставить комментарий');
  await d.click(modal.getByRole('button', { name: 'Отметить' }), 'Подтвердите');
  await expect(modal).toBeHidden();
  // Настоящая мышь осталась над модальным окном — уводим её.
  await page.mouse.move(1100, 180);

  await expect(flagBar).toContainText(`· ${countBefore - 1}`);
  await d.caption('Замечание снято — задача ушла из списка проблемных');
  await d.show(flagBar);
  await d.pause(1700);

  const showReviewed = filters.locator('.ant-switch').first();
  await d.click(showReviewed, '«показывать просмотренные» вернёт отметку приглушённым значком');
  await expect(row).toBeVisible();
  await d.show(flagChip);
  await d.pause(1700);

  await d.click(flagChip, 'Значок приглушён — нажмите на него');
  await d.click(
    page.locator('.ant-dropdown-menu-item', { hasText: 'Вернуть в проблемные' }),
    'Если отметили по ошибке — снимите её',
  );
  await page.mouse.move(1100, 180);
  await d.pause(900);

  await d.click(showReviewed, 'Выключите переключатель — вернётесь к обычному виду');
  await expect(flagBar).toContainText(`· ${countBefore}`);
  await d.pause(1600);

  await d.click(flagChip, 'Разобрались по задаче — отметьте её снова');
  await d.click(page.locator('.ant-dropdown-menu-item', { hasText: 'Просмотрено' }), 'Выберите «Просмотрено»');
  await expect(modal).toBeVisible();
  await d.pause(300);
  await d.click(modal.getByRole('button', { name: 'Отметить' }), 'Подтвердите');
  await expect(modal).toBeHidden();
  await page.mouse.move(1100, 180);
  await expect(flagBar).toContainText(`· ${countBefore - 1}`);

  await d.caption('Готово', 3000);
  await d.show(flagBar);
  await d.pause(700);
  await d.save('team-desk-stuck');
});
