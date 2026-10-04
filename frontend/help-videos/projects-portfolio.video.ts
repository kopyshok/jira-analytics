// Ролик «Как посмотреть портфель квартала и план проекта»: Проекты — квартал,
// «Сводка» (кольца этапов, таблица «Проекты портфеля» — сортировка и раскрытие
// задач, «Таймлайн портфеля», сигналы) → клик по проекту → «Анализ» (структура
// трудозатрат, участники, статус) → «Презентация» → «План и сроки» (кольца,
// таймлайн фаз, задачи проекта) → «PNG». Подпись проговаривает: даты фаз в
// «Плане и сроках» — из ресурсного плана команды. Список слева намеренно
// открывается на текущем квартале, а не на квартале шапки — ролик показывает
// это и переключает квартал вручную (см. отчёт координатору).
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const HEADER_YEAR = 2026;
// Прошлый квартал: и в нём, и в «текущем» (Q3, откроется по умолчанию) уже
// есть реальные списания — оба богаты данными для показа. Будущий Q4 непоказателен:
// утверждённый сценарий есть, а фактических часов пока нет.
const HEADER_QUARTER = 2;
const LIST_QUARTER = 2;

interface PortfolioProject {
  key: string;
  title: string | null;
  total_fact: number;
}

let projectKey = '';
let projectTitle = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.put(`${api}/users/me/period`, { data: { year: HEADER_YEAR, quarter: HEADER_QUARTER } }));

  const portfolioRes = await request.get(`${api}/projects/portfolio`, {
    params: { year: HEADER_YEAR, quarter: LIST_QUARTER, teams: TEAM },
  });
  ok(portfolioRes);
  const portfolio = (await portfolioRes.json()) as { projects: PortfolioProject[] };
  const best = [...portfolio.projects].sort((a, b) => b.total_fact - a.total_fact)[0];
  expect(best, `Нет проектов портфеля команды ${TEAM} за Q${LIST_QUARTER} ${HEADER_YEAR}`).toBeTruthy();
  projectKey = best.key;
  projectTitle = best.title ?? best.key;

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

test('projects-portfolio', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/projects', 'Как посмотреть портфель квартала и план проекта');
  const portfolioView = page.locator('[data-testid="portfolio-view"]');
  await expect(portfolioView).toBeVisible({ timeout: 20_000 });
  await d.pause(1000);
  await d.poster();
  await d.pause(500);

  // Список слева живёт на текущем квартале сервиса, а не на квартале шапки.
  const activeQuarterTag = page.locator('[data-testid="projects-quarter-tag"].ant-tag-cyan');
  await d.caption('Квартал списка проектов выбирается отдельно — над списком');
  await d.show(page.locator('[data-tour="header-period"]'), activeQuarterTag);
  await d.pause(500);
  await d.click(page.locator(`[data-testid="projects-quarter-tag"][data-quarter="${LIST_QUARTER}"]`), 'Выберите нужный квартал в списке вручную');
  await expect(portfolioView.locator('[data-testid="portfolio-projects-table"] .ant-table-row').first()).toBeVisible({ timeout: 15_000 });

  await d.caption('«Сводка» — кольца по этапам и загрузка всего портфеля');
  await d.show(portfolioView);
  await d.pause(500);

  const table = portfolioView.locator('[data-testid="portfolio-projects-table"]');
  await d.click(table.locator('th', { hasText: 'Факт / План' }), 'Таблицу «Проекты портфеля» можно отсортировать по любой колонке');
  await d.pause(1200);

  const projectRow = table.locator('.ant-table-row', { hasText: projectTitle }).first();
  await expect(projectRow).toBeVisible();
  const expandIcon = projectRow.locator('.ant-table-row-expand-icon');
  if (await expandIcon.count()) {
    await d.click(expandIcon, 'Стрелка раскрывает задачи проекта прямо в таблице');
    await d.pause(500);
  }

  const timelineCard = page.locator('.ant-card', { hasText: 'Таймлайн портфеля' });
  await timelineCard.scrollIntoViewIfNeeded();
  await d.caption('Таймлайн портфеля — фазы каждого проекта относительно сегодняшнего дня');
  await d.show(timelineCard);
  await d.pause(500);

  const signals = page.locator('[data-testid="portfolio-signals"]');
  if (await signals.count()) {
    await d.caption('Внизу — сигналы: куда стоит посмотреть в первую очередь');
    await d.show(signals);
    await d.pause(500);
  }

  // Клик по проекту → карточка, вид «Анализ».
  await d.waitVoice();
  await d.click(projectRow, `Откройте проект «${projectTitle}»`);
  await expect(page).toHaveURL(new RegExp(`/projects/${encodeURIComponent(projectKey)}`), { timeout: 15_000 });
  const headerActions = page.locator('.project-header-actions');
  await expect(headerActions).toBeVisible({ timeout: 15_000 });
  await d.pause(900);

  const categoriesCard = page.locator('.ant-card', { hasText: 'Структура трудозатрат' });
  await expect(categoriesCard).toBeVisible({ timeout: 15_000 });
  await d.caption('«Анализ» — структура трудозатрат по всему проекту');
  await d.show(categoriesCard);
  await d.pause(500);

  const employeesCard = page.locator('.ant-card', { hasText: 'Участники' });
  await d.caption('Участники и часы каждого');
  await d.show(employeesCard);
  await d.pause(500);

  const statusCard = page.locator('.ant-card', { hasText: 'Статус проекта' });
  await d.caption('Статус проекта — короткая сводка и ключевые цифры');
  await d.show(statusCard);
  await d.pause(500);

  // Презентация.
  await d.waitVoice();
  await d.click(headerActions.getByRole('button', { name: 'Презентация' }), 'Вид «Презентация» — тот же проект одной страницей для встречи');
  await expect(page.locator('.presentation-view')).toBeVisible({ timeout: 15_000 });
  await d.pause(500);

  // План и сроки.
  await d.waitVoice();
  await d.click(headerActions.getByRole('button', { name: 'План и сроки' }), 'А «План и сроки» — план по этапам и даты фаз');
  const planTimelineCard = page.locator('.ant-card', { hasText: 'Таймлайн проекта' });
  await expect(planTimelineCard).toBeVisible({ timeout: 15_000 });
  await d.caption('Даты фаз здесь берутся из ресурсного плана команды');
  await d.show(planTimelineCard);
  await d.pause(500);

  const tasksCard = page.locator('.ant-card', { hasText: 'Задачи проекта' });
  await d.caption('Ниже — задачи проекта с часами');
  await d.show(tasksCard);
  await d.pause(500);

  // Сохранение картинки.
  await d.waitVoice();
  const downloadPromise = page.waitForEvent('download', { timeout: 20_000 });
  await d.click(headerActions.getByRole('button', { name: 'PNG' }), 'Сохраните картинку — презентация уйдёт в файл');
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.png$/);
  await d.pause(900);
  await d.caption('Файл сохранён — можно вставить в письмо или отчёт');
  await d.show(page.locator('.presentation-view'));
  await d.pause(500);

  await d.caption('Готово', 4200);
  await d.save('projects-portfolio');
});
