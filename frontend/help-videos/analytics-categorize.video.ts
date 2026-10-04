// Ролик «Как разобрать часы без категории прямо из отчёта»: Аналитика → строка
// «Не указана категория/вид работ» → задача → карточка → «Категория и анализ»:
// выбрать категорию, сохранить → часы ушли в нужный вид работ. Заодно — плитка
// «Чужих часов» и вид работ «Прочие / Чужие задачи».
import { expect, test, type Locator, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const CATEGORY = 'Технические задачи';
const ORPHAN_LABEL = 'Не указана категория/вид работ';

interface ReportShape {
  grand_totals: { foreign_hours: number };
  teams: { roles: { employees: { work_types: { label: string }[] }[] }[] }[];
}

/** Найти квартал команды, где в отчёте реально есть часы без категории —
 *  без этого строка «Не указана категория/вид работ» не появится в дереве. */
async function findOrphanQuarter(
  page: Page, api: string, team: string,
): Promise<{ year: number; quarter: number; report: ReportShape } | null> {
  const now = new Date();
  const years = [now.getFullYear(), now.getFullYear() - 1];
  for (const year of years) {
    for (let quarter = 4; quarter >= 1; quarter--) {
      const res = await page.request.get(`${api}/analytics/report`, {
        params: { year, quarter, teams: team },
      });
      if (!res.ok()) continue;
      const report = (await res.json()) as ReportShape;
      const hasOrphan = report.teams.some((t) =>
        t.roles.some((r) => r.employees.some((e) => e.work_types.some((w) => w.label === ORPHAN_LABEL))),
      );
      if (hasOrphan) return { year, quarter, report };
    }
  }
  return null;
}

/**
 * Открыть выпадающий список категорий и выбрать нужную. Список рендерится
 * виртуально (AntD Select) и открывается со скроллом к уже стоящему значению —
 * нужная опция может быть не отрисована вовсе, пока к ней не прокрутить.
 */
async function pickCategory(d: Director, page: Page, trigger: Locator, label: string, caption?: string): Promise<void> {
  await d.click(trigger, caption);
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown).toBeVisible();
  const option = dropdown.locator('.ant-select-item-option', { hasText: label });
  await dropdown.hover();
  for (let i = 0; i < 20 && (await option.count()) === 0; i++) {
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(80);
  }
  await expect(option.first()).toBeVisible({ timeout: 5_000 });
  await d.click(option.first());
}

test.afterAll(async ({ playwright }, testInfo) => {
  // Шапку возвращаем на демо-команду без групп — на случай, если ролик сменит её.
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

async function setLayout(page: Page, api: string) {
  expect((await page.request.put(`${api}/users/me/analytics-layout`, {
    data: {
      layout: {
        group_order: ['work_type', 'category', 'issue', 'team', 'subgroup', 'role', 'employee'],
        hidden_levels: ['team', 'subgroup', 'role', 'employee'],
        active_preset: 'work_types',
        show_fact_bar: true,
      },
    },
  })).ok()).toBeTruthy();
}

test('analytics-categorize', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, {
    data: { teams: [TEAM], subgroups: [] },
  })).ok()).toBeTruthy();

  const found = await findOrphanQuarter(page, api, TEAM);
  expect(found, `У команды ${TEAM} нет ни одного квартала (за 2 года) с часами без категории`).toBeTruthy();
  const { year: YEAR, quarter: QUARTER, report } = found!;
  expect((await page.request.put(`${api}/users/me/period`, {
    data: { year: YEAR, quarter: QUARTER },
  })).ok()).toBeTruthy();
  // «По видам работ»: вид работ сразу вверху дерева — не нужно раскрывать
  // роль и сотрудника, чтобы добраться до «Не указана категория/вид работ».
  await setLayout(page, api);

  const hasForeign = report.grand_totals.foreign_hours > 0;

  await d.open('/analytics', 'Как разобрать часы без категории прямо из отчёта');
  const table = page.locator('[data-tour="analytics-table"]');
  await expect(table.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 20_000 });
  await d.pause(1000);
  await d.poster();
  await d.pause(500);

  await d.caption('Настройка «По видам работ» держит вид работ вверху дерева');
  await d.show(page.locator('[data-tour="analytics-settings"]'));
  await d.pause(500);

  const orphanRow = table.locator('tr.tree-row-depth-0', { hasText: ORPHAN_LABEL });
  await expect(orphanRow).toBeVisible({ timeout: 15_000 });
  await d.click(orphanRow, 'Часть часов лежит без категории — раскройте строку');
  const orphanCategoryRow = table.locator('tr.tree-row-depth-1').first();
  await expect(orphanCategoryRow).toBeVisible();
  await d.click(orphanCategoryRow, 'Дальше — сами задачи');
  const orphanIssueRow = table.locator('tr.tree-row-depth-2').first();
  await expect(orphanIssueRow).toBeVisible();
  await d.show(orphanIssueRow);
  await d.pause(500);

  await d.click(orphanIssueRow.locator('span[style*="flex: 1 1 auto"]').first(), 'Откройте задачу');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible({ timeout: 10_000 });
  const contextBlock = drawer.getByText('Контекст', { exact: true });
  await d.caption('Справа — карточка с контекстом задачи');
  await d.show(contextBlock);
  await d.pause(500);

  const categorizeBlock = drawer.locator('[data-tour="analytics-categorize"]');
  await d.caption('Блок «Категория и анализ» — прямо в карточке задачи');
  await d.show(categorizeBlock);
  await d.pause(500);

  const subtreeCheck = drawer.getByText('Применить ко всему поддереву');
  if (await subtreeCheck.count()) {
    await d.caption('Галочка «Применить ко всему поддереву» поставит категорию и подзадачам');
    await d.show(subtreeCheck);
    await d.waitVoice();
  }

  await pickCategory(d, page, categorizeBlock.locator('.ant-select'), CATEGORY, 'Выберите категорию');
  await d.click(categorizeBlock.getByRole('button', { name: 'Сохранить' }), 'Сохраните');
  await d.pause(800);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();

  await d.caption('Категория задачи решает, в какой вид работ пойдут часы');
  await expect(table.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 15_000 });
  await d.show(table.locator('tr.tree-row-depth-0').first());
  await d.pause(500);

  const thematicArrow = table.locator('tr.tree-row-depth-0 .anticon-arrow-right').first();
  if (await thematicArrow.count()) {
    await d.caption('Стрелка у вида работ открывает «Тематический отчёт»');
    await d.show(thematicArrow);
    await d.pause(300);
  }

  await d.caption('Плитка «Чужих часов» — списания на задачи других команд');
  await d.show(page.locator('[data-tour="analytics-kpi"] > div', { hasText: 'Чужих часов' }));
  await d.pause(500);

  await d.caption('А общий итог по факту и плану — в плитках сверху');
  await d.show(page.locator('[data-tour="analytics-kpi"]'));
  await d.pause(500);

  await d.caption('Кнопка выгрузки в Эксель сохраняет тот же срез в файл');
  await d.show(page.getByRole('button', { name: 'Экспорт XLSX' }));
  await d.pause(500);

  await d.caption('Переключатель «Иерархия» покажет задачи деревом до родителя');
  await d.show(page.locator('[data-tour="analytics-hierarchy"]'));
  await d.pause(500);

  if (hasForeign) {
    const foreignRow = table.locator('tr.tree-row-depth-0', { hasText: 'Прочие / Чужие задачи' });
    if (await foreignRow.count()) {
      await d.click(foreignRow, 'Вид работ «Прочие, чужие задачи» — сюда попадают чужие списания');
      const categoryRows = table.locator('tr.tree-row-depth-1');
      const catCount = Math.min(await categoryRows.count(), 4);
      let foreignIssue = table.locator('tr.tree-row-depth-2', { hasText: 'Чужая' }).first();
      for (let i = 0; i < catCount && (await foreignIssue.count()) === 0; i++) {
        await d.click(categoryRows.nth(i));
        foreignIssue = table.locator('tr.tree-row-depth-2', { hasText: 'Чужая' }).first();
      }
      if (await foreignIssue.count()) {
        await d.caption('Метка «Чужая» — задача принадлежит другой команде');
        await d.show(foreignIssue);
        await d.pause(500);
      }
    }
  }

  await d.caption('Готово', 2200);
  await d.save('analytics-categorize');
});
