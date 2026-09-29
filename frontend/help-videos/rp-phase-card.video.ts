// Ролик «Что показывает карточка фазы»: полоса на диаграмме (по возможности —
// на критическом пути) → карточка справа → основные поля → шестерёнка
// «Показывать секции» открывает «Откуда дата старта», «Дни × часы» и
// «Критический путь» (если фаза на нём).
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { phaseBar, prepareQuarterPlan } from './rp-setup.ts';

type FullAssignment = {
  backlog_item_id: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  part_number: number;
  employee_id: string | null;
  is_on_critical_path: boolean;
};

test('rp-phase-card', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { rp, plan } = await prepareQuarterPlan(page);
  const full: { assignments: FullAssignment[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const withEmployee = full.assignments.filter((a) => a.employee_id);
  const target = withEmployee.find((a) => a.is_on_critical_path) ?? withEmployee[0];
  if (!target) throw new Error('В плане нет фаз с исполнителем');

  // Секции детализации скрыты заранее — в ролике их включает шестерёнка.
  const prefs = await page.request.patch(`${rp}/preferences`, {
    data: {
      detail_sections_visible: {
        algorithm: false, day_table: false, absences: false, sources: false, duration: false, critical_path: false,
      },
    },
  });
  expect(prefs.ok()).toBeTruthy();

  const bar = phaseBar(page, target);

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Что показывает карточка фазы');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(bar).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(700);
  await d.poster();
  await d.pause(1200);

  await d.click(bar, 'Нажмите на полосу фазы на диаграмме');
  const drawer = page.getByRole('dialog');
  await expect(drawer).toBeVisible();
  const row = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) });

  await d.caption('Справа открывается карточка фазы');
  await d.show(row('Сотрудник'), row('Вовлечённость'));
  await d.pause(1000);
  await d.caption('Даты начала и окончания — рассчитаны сервисом');
  await d.show(row('Начало'), row('Окончание'));
  await d.pause(1200);

  if (target.is_on_critical_path) {
    const cpTag = drawer.locator('.ant-tag', { hasText: 'Критический путь' });
    await expect(cpTag).toBeVisible();
    await d.caption('Красная рамка и метка — фаза на критическом пути');
    await d.show(cpTag);
    await d.pause(1200);
  }

  // Шестерёнка «Показывать секции» — включаем разбор расчёта.
  const gear = drawer.getByRole('button', { name: 'setting' });
  await d.click(gear, 'Откройте «Показывать секции»');
  const popover = page.locator('.ant-popover:visible', { hasText: 'Показывать секции' });
  await expect(popover).toBeVisible();
  await d.click(popover.locator('label', { hasText: 'Откуда дата старта' }), 'Включите «Откуда дата старта»');
  await d.click(popover.locator('label', { hasText: 'Дни × часы' }), 'И «Дни × часы»');
  if (target.is_on_critical_path) {
    await d.click(popover.locator('label', { hasText: 'Критический путь' }));
  }
  // Закрыть окно секций тем же щелчком по шестерёнке — щелчок по маске задней
  // области закрыл бы саму карточку фазы, а не только это окно.
  await d.click(gear);
  await expect(popover).toBeHidden();

  const algoSection = drawer.getByText('Откуда дата старта').last();
  await algoSection.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('Здесь сервис объясняет, откуда взялась дата начала');
  await d.show(algoSection);
  await d.pause(1600);

  const dayTable = drawer.getByText('Дни × часы').last();
  await dayTable.scrollIntoViewIfNeeded();
  await d.caption('А здесь — по каким дням и сколько часов разложена работа');
  await d.show(dayTable);
  await d.pause(1800);

  await d.caption('Готово', 2200);
  await d.save('rp-phase-card');
});
