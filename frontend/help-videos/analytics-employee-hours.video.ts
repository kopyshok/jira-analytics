// Ролик «Как посмотреть, куда ушли часы сотрудника»: Аналитика → команда и квартал
// в шапке, плитки итогов, список команд → «Настройка отчёта» → раскрыть роль →
// сотрудник → вид работ → категория → задача → карточка задачи, «Ворклоги за
// период» → переключатель «Иерархия» → «Экспорт XLSX».
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const YEAR = 2026;
const QUARTER = 3;

test('analytics-employee-hours', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);

  // Тот же квартал и та же команда при любом запуске — иначе на «сегодня»
  // могло попасть пустое полугодие без ворклогов.
  expect((await page.request.put(`${api}/api/v1/auth/me/teams`, {
    data: { teams: [TEAM], subgroups: [] },
  })).ok()).toBeTruthy();
  expect((await page.request.put(`${api}/api/v1/users/me/period`, {
    data: { year: YEAR, quarter: QUARTER },
  })).ok()).toBeTruthy();
  // Раскладка отчёта — стандартная, независимо от того, что настраивали в других
  // роликах: депту 0..4 строк дальше по сценарию соответствуют роль/сотрудник/
  // вид работ/категория/задача только при этом порядке уровней.
  expect((await page.request.put(`${api}/api/v1/users/me/analytics-layout`, {
    data: {
      layout: {
        group_order: ['team', 'subgroup', 'role', 'employee', 'work_type', 'category', 'issue'],
        hidden_levels: ['subgroup'],
        active_preset: 'default',
        show_fact_bar: true,
      },
    },
  })).ok()).toBeTruthy();

  await d.open('/analytics', 'Как посмотреть, куда ушли часы сотрудника');
  const table = page.locator('[data-tour="analytics-table"]');
  await expect(table.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 20_000 });
  await d.pause(1000);
  await d.poster();
  await d.pause(2200);

  await d.caption('Команда и квартал берутся из шапки приложения');
  await d.show(page.locator('[data-tour="header-team"]'), page.locator('[data-tour="header-period"]'));
  await d.pause(2000);

  await d.caption('Плитки — итоги по факту, плану и выполнению');
  await d.show(page.locator('[data-tour="analytics-kpi"]'));
  await d.pause(2200);

  await d.caption('Слева — список команд, отчёт можно смотреть по каждой отдельно');
  await d.show(page.locator('.ant-card', { hasText: 'Команды' }));
  await d.pause(2000);

  await d.click(page.locator('[data-tour="analytics-settings"]'), 'В «Настройке отчёта» — группировка, столбцы и визуализация');
  const settingsModal = page.locator('.ant-modal', { hasText: 'Настройка отчёта' });
  await expect(settingsModal).toBeVisible();
  await d.show(settingsModal.locator('.ant-btn', { hasText: 'Стандарт' }));
  await d.pause(2000);
  await page.keyboard.press('Escape');
  await expect(settingsModal).toBeHidden();

  await d.caption('Клик по задаче откроет карточку справа — так решает переключатель «Ворклоги»');
  await d.show(page.getByText('Ворклоги:', { exact: true }));
  await d.pause(2000);

  // Дерево свёрнуто по умолчанию: раскрываем роль → сотрудника → вид работ → категорию.
  await d.caption('Раскройте роль, сотрудника, вид работ и категорию');
  await d.click(table.locator('tr.tree-row-depth-0.tree-row-has-children').first());
  await d.click(table.locator('tr.tree-row-depth-1.tree-row-has-children').first());
  await d.click(table.locator('tr.tree-row-depth-2.tree-row-has-children').first());
  await d.click(table.locator('tr.tree-row-depth-3.tree-row-has-children').first());

  const issueRow = table.locator('tr.tree-row-depth-4').first();
  await expect(issueRow).toBeVisible();
  await d.caption('Категория — и сразу видно конкретную задачу');
  await d.show(issueRow);
  await d.pause(1800);

  await d.click(issueRow, 'Откройте задачу — справа карточка с контекстом');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible({ timeout: 10_000 });
  const contextBlock = drawer.getByText('Контекст', { exact: true });
  await d.caption('«Контекст» — цепочка родителей задачи');
  await d.show(contextBlock);
  await d.pause(1800);

  const worklogsBlock = drawer.getByText('Ворклоги за период', { exact: true });
  await d.caption('«Ворклоги за период» — все списания по задаче');
  await d.show(worklogsBlock);
  await d.pause(2200);
  await page.keyboard.press('Escape');
  await expect(drawer).toBeHidden();

  await d.caption('Переключатель «Иерархия» показывает задачи деревом до родителя');
  await d.click(page.locator('[data-tour="analytics-hierarchy"] .ant-switch'));
  await d.pause(2200);

  await d.caption('«Экспорт XLSX» выгружает этот же срез в файл');
  await d.show(page.getByRole('button', { name: 'Экспорт XLSX' }));
  await d.pause(2400);

  await d.caption('Цвет цифры в «Часы факт» — по проценту выполнения плана');
  await d.show(table.locator('tr.tree-row-depth-4').first());
  await d.pause(2600);

  await d.caption('Любая смена фильтра сразу пересчитывает и плитки, и таблицу');
  await d.show(page.locator('[data-tour="analytics-kpi"]'));
  await d.pause(2800);

  await d.caption('Готово', 2200);
  await d.save('analytics-employee-hours');
});
