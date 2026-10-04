// Ролик «Как собрать одностраничник проекта»: Проекты → квартал над списком →
// поиск проекта по ключу → карточка → «Анализ» (структура трудозатрат,
// участники, статус, топ задач) → «Презентация» → сохранение картинки.
// «Цели проекта» и «Основной результат» без ИИ пусты — в кадре не акцентируются.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const HEADER_YEAR = 2026;
// Квартал с реальными списаниями (в нём есть и участники, и топ задач).
const QUARTER = 2;

interface PortfolioProject {
  key: string;
  title: string | null;
  total_fact: number;
}

let projectKey = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.put(`${api}/users/me/period`, { data: { year: HEADER_YEAR, quarter: QUARTER } }));

  const portfolioRes = await request.get(`${api}/projects/portfolio`, {
    params: { year: HEADER_YEAR, quarter: QUARTER, teams: TEAM },
  });
  ok(portfolioRes);
  const portfolio = (await portfolioRes.json()) as { projects: PortfolioProject[] };
  const best = [...portfolio.projects].sort((a, b) => b.total_fact - a.total_fact)[0];
  expect(best, `Нет проектов портфеля команды ${TEAM} за второй квартал ${HEADER_YEAR}`).toBeTruthy();
  projectKey = best.key;

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.put(`${api}/users/me/period`, { data: { year: 2026, quarter: 3 } });
  await request.dispose();
});

test('projects-card', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/projects', 'Как собрать одностраничник проекта');
  const portfolioView = page.locator('[data-testid="portfolio-view"]');
  await expect(portfolioView).toBeVisible({ timeout: 20_000 });
  await d.pause(900);
  await d.poster();
  await d.pause(1200);

  await d.click(page.locator(`[data-testid="projects-quarter-tag"][data-quarter="${QUARTER}"]`), 'Выберите квартал над списком проектов');
  await expect(portfolioView.locator('[data-testid="portfolio-projects-table"] .ant-table-row').first()).toBeVisible({ timeout: 15_000 });
  await d.waitVoice();

  const search = page.getByPlaceholder('Поиск по названию или ключу');
  await d.type(search, projectKey, 'Найдите нужный проект по ключу или названию');
  await d.caption('Ниже поиска — фильтры по статусу и по типу проекта');
  await d.show(page.getByText('В работе', { exact: true }).first(), page.getByText('Архив', { exact: true }).first());
  await d.waitVoice();
  const card = page.locator('[data-testid="project-card"]').first();
  await expect(card).toBeVisible({ timeout: 10_000 });
  await d.waitVoice();
  await d.click(card, 'Откройте карточку проекта');
  await expect(page).toHaveURL(new RegExp(`/projects/${encodeURIComponent(projectKey)}`), { timeout: 15_000 });
  const headerActions = page.locator('.project-header-actions');
  await expect(headerActions).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(1100, 160);
  await d.pause(600);

  const categoriesCard = page.locator('.ant-card', { hasText: 'Структура трудозатрат' });
  await expect(categoriesCard).toBeVisible({ timeout: 15_000 });
  await d.caption('«Анализ» — структура трудозатрат по всему проекту');
  await d.show(categoriesCard);
  await d.pause(400);

  await d.caption('Участники и часы каждого — из списаний в Jira');
  await d.show(page.locator('.ant-card', { hasText: 'Участники' }));
  await d.pause(400);

  await d.caption('Справа — статус проекта с ключевыми цифрами');
  await d.show(page.locator('.ant-card', { hasText: 'Статус проекта' }));
  await d.pause(400);

  await d.caption('Ниже — три задачи, на которые ушло больше всего часов');
  await d.show(page.locator('.ant-card', { hasText: 'Топ-3 задачи' }));
  await d.waitVoice();

  await d.click(headerActions.getByRole('button', { name: 'Презентация' }), '«Презентация» — тот же проект одной страницей для встречи');
  await expect(page.locator('.presentation-view')).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(1100, 160);
  await d.waitVoice();

  await d.click(headerActions.getByRole('button', { name: 'План и сроки' }), 'Во вкладке «План и сроки» — даты фаз из ресурсного плана команды');
  await expect(page.locator('.ant-card', { hasText: 'Таймлайн проекта' })).toBeVisible({ timeout: 15_000 });
  await d.show(page.locator('.ant-card', { hasText: 'Таймлайн проекта' }));
  await d.waitVoice();
  await d.click(headerActions.getByRole('button', { name: 'Презентация' }), 'Вернитесь к «Презентации» — она и станет одностраничником');
  await expect(page.locator('.presentation-view')).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(1100, 160);
  await d.waitVoice();

  const downloadPromise = page.waitForEvent('download', { timeout: 20_000 });
  await d.click(headerActions.getByRole('button', { name: 'PNG' }), 'Сохраните картинку — вставьте её в письмо или отчёт');
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.png$/);
  await d.waitVoice();
  await d.caption('Файл сохранён — одностраничник готов');
  await d.show(page.locator('.presentation-view'));
  await d.waitVoice();

  await d.caption('Готово', 2200);
  await d.save('projects-card');
});
