// Ролик «Как сообщить об ошибке или предложить идею»: круглая кнопка в углу любой
// страницы → «Открыть форму» → «Идея» → отправка → раздел «Обратная связь»:
// «Мои обращения» (открыть обращение), «Лента идей», «Создать» → «Баг»,
// «Быстрый баг» (только показываем). Созданное обращение удаляем из копии базы в afterAll.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const IDEA_TITLE = 'Отчёт по остаткам';
const IDEA_BODY = 'Нужен отчёт по остаткам на складе';

function runDbPath(): string {
  const port = process.env.VIDEOS_BACKEND_PORT ?? '8012';
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

/** Убрать обращения этого ролика (в интерфейсе удалять их нельзя). */
function cleanFeedback(): void {
  try {
    const db = new DatabaseSync(runDbPath());
    db.exec('PRAGMA busy_timeout=5000');
    try {
      db.prepare('DELETE FROM feedback_items WHERE title IN (?, ?)').run(IDEA_TITLE, 'Быстрый баг-репорт');
    } finally {
      db.close();
    }
  } catch {
    // Файл занят сервером — не роняем ролик из-за уборки.
  }
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  await request.dispose();
  cleanFeedback();
});

test.afterAll(() => {
  cleanFeedback();
});

test('feedback-send', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/backlog', 'Как сообщить об ошибке или предложить идею');
  await expect(page.locator('[data-tour="backlog-tabs"] tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const group = page.locator('.ant-float-btn-group');
  await expect(group).toBeVisible();
  await d.caption('В углу любой страницы — круглая кнопка с двумя действиями');
  await d.show(group);
  await d.pause(800);

  await d.point(group);
  await group.hover();
  const formBtn = page.locator('.ant-float-btn-group .ant-float-btn:has(.anticon-comment)').first();
  const quickBtn = page.locator('.ant-float-btn-group .ant-float-btn:has(.anticon-thunderbolt)');
  await expect(quickBtn).toBeVisible();
  await d.pause(900);
  await d.click(formBtn, 'Нажмите «Открыть форму»');

  const drawer = page.locator('.ant-drawer-open', { hasText: 'Обратная связь' });
  await expect(drawer).toBeVisible();
  await page.mouse.move(700, 120);
  await d.click(drawer.locator('label.ant-radio-button-wrapper', { hasText: 'Идея' }), 'Выберите «Идея»');
  await d.type(drawer.getByPlaceholder('Суть идеи одной строкой'), IDEA_TITLE, 'Заголовок — суть идеи одной строкой');
  await d.type(drawer.locator('textarea').first(), IDEA_BODY);
  await d.click(drawer.getByRole('button', { name: 'Отправить' }), 'Отправьте');
  await expect(drawer).toBeHidden();
  await page.mouse.move(700, 120);
  await d.caption('Идея ушла администратору');
  await d.pause(300);

  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Обратная связь' }), 'Свои обращения — в разделе «Обратная связь»');
  const table = page.locator('.ant-tabs-tabpane-active .ant-table');
  const row = table.locator('tbody tr', { hasText: IDEA_TITLE });
  await expect(row).toBeVisible({ timeout: 15_000 });
  await d.caption('На вкладке «Мои обращения» — всё, что вы отправили');
  await d.show(row);
  await d.pause(600);

  await d.click(row, 'Щёлкните по строке — обращение откроется целиком');
  const detail = page.locator('.ant-drawer-open', { hasText: 'Описание' });
  await expect(detail).toBeVisible();
  await d.pause(900);
  await d.waitVoice();
  await d.click(detail.locator('.ant-drawer-close'));
  await expect(detail).toBeHidden();

  await d.click(page.getByRole('tab', { name: 'Лента идей' }), 'В «Ленте идей» — идеи всех сотрудников');
  await expect(page.locator('.ant-tabs-tabpane-active .ant-table tbody tr').first()).toBeVisible();
  await d.caption('Загляните сюда перед отправкой — такую идею могли уже предложить');
  await d.show(page.locator('.ant-tabs-tabpane-active .ant-table'));
  await d.pause(600);
  await d.waitVoice();

  await d.click(page.getByRole('button', { name: /Создать/ }), 'Кнопка «Создать» открывает ту же форму');
  const form = page.locator('.ant-drawer-open', { hasText: 'Обратная связь' });
  await expect(form).toBeVisible();
  await d.click(form.locator('label.ant-radio-button-wrapper', { hasText: 'Баг' }));
  await d.caption('К багу сервис сам прикладывает страницу, команду и период');
  await d.show(form.getByPlaceholder('Что не работает (одной строкой)'));
  await d.pause(600);
  await d.waitVoice();
  await d.click(form.getByRole('button', { name: 'Отмена' }));
  await expect(form).toBeHidden();
  await page.mouse.move(700, 120);

  await d.point(group);
  await group.hover();
  await expect(quickBtn).toBeVisible();
  await d.caption('Быстрый баг уходит одним нажатием, вместе с контекстом страницы');
  await d.show(quickBtn);
  await page.mouse.move(await quickBtn.evaluate((el) => el.getBoundingClientRect().x + 10),
    await quickBtn.evaluate((el) => el.getBoundingClientRect().y + 10));
  await d.pause(800);
  await d.waitVoice();

  await page.mouse.move(700, 120);
  await d.pause(300);

  await d.caption('Готово', 2200);
  await d.save('feedback-send');
});
