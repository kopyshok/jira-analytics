// Ролик «Как смотреть план: задачи, исполнители, масштаб»: вид «Исполнители»
// (дорожка на человека, штриховка — работа в другой команде) → фильтр по
// одному человеку (полосы подсвечены) → масштаб «Месяц»/«Неделя» → назад
// в «Задачи» → «Свернуть все».
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { prepareQuarterPlan } from './rp-setup.ts';

type FullAssignment = { employee_id: string | null; employee_name: string | null };
type FullBooking = { employee_id: string; team: string };
type FullGantt = { assignments: FullAssignment[]; external_bookings?: FullBooking[] };

test('rp-views', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { rp, plan } = await prepareQuarterPlan(page);

  // Кто-то с фазами в этом плане, у кого есть и чужая бронь — на нём видна штриховка.
  const full: FullGantt = await (await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)).json();
  const assignedIds = new Set(full.assignments.filter((a) => a.employee_id).map((a) => a.employee_id as string));
  const booking = (full.external_bookings ?? []).find((b) => assignedIds.has(b.employee_id));
  const targetId = booking?.employee_id ?? full.assignments.find((a) => a.employee_id)?.employee_id ?? null;
  if (!targetId) throw new Error('В плане нет фаз с исполнителем');
  const targetName = full.assignments.find((a) => a.employee_id === targetId)?.employee_name ?? '';
  if (!targetName) throw new Error('У исполнителя не найдено имя');

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как смотреть план: задачи, исполнители, масштаб');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(page.locator('[data-testid^="rp-bar-"]').first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(700);
  await d.poster();
  await d.pause(1200);

  // Переключение на вид «Исполнители»: секция на человека вместо секции на задачу.
  const peopleToggle = page.locator('.ant-segmented-item', { hasText: 'Исполнители' });
  await d.click(peopleToggle, 'Переключитесь на вид «Исполнители»');
  const allWork = page.getByText('Все работы').first();
  await expect(allWork).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('У каждого человека — своя дорожка со всеми его делами');
  await d.show(allWork);
  await d.pause(1200);

  if (booking) {
    const hatch = page.locator(`[title*="${booking.team}"]`).first();
    if (await hatch.count()) {
      await expect(hatch).toBeVisible();
      await d.caption('Серая штриховка — человек занят в другой команде');
      await hatch.scrollIntoViewIfNeeded();
      await d.show(hatch);
      await d.pause(1400);
    }
  }

  // Фильтр по одному человеку — щелчок по имени в заголовке его секции.
  const header = page.locator('[role="button"][aria-pressed]').filter({ hasText: targetName }).first();
  await d.click(header, 'Нажмите на имя — останутся только его работы');
  await expect(header).toHaveAttribute('aria-pressed', 'true');
  const highlightedBar = page.locator('[data-testid^="rp-bar-"]').first();
  await expect(highlightedBar).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('Полосы одного исполнителя подсвечены');
  await d.show(highlightedBar);
  await d.pause(1200);

  // Масштаб таймлайна: неделя ↔ месяц.
  await d.click(page.locator('.ant-segmented-item', { hasText: 'Месяц' }), 'Масштаб можно менять — месяцами…');
  await d.pause(900);
  await d.click(page.locator('.ant-segmented-item', { hasText: 'Неделя' }), '…или неделями, для деталей');
  await d.pause(900);

  // Снять фильтр и вернуться к виду «Задачи».
  await d.click(header, 'Снимите фильтр по человеку');
  await expect(header).toHaveAttribute('aria-pressed', 'false');
  await d.click(page.locator('.ant-segmented-item', { hasText: 'Задачи' }), 'Вернитесь к виду «Задачи»');
  await expect(page.locator('[data-testid^="rp-bar-"]').first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(800);

  // «Вид» → «Свернуть все».
  const viewBtn = page.locator('[data-tour="rp-view"]');
  await d.click(viewBtn, 'В окне «Вид» можно свернуть все задачи');
  const collapseBtn = page.locator('.ant-popover:visible button', { hasText: 'Свернуть все' });
  await expect(collapseBtn).toBeVisible();
  await d.click(collapseBtn);
  await d.click(viewBtn); // закрыть окно тем же щелчком по кнопке «Вид»
  await expect(page.locator('.ant-popover:visible')).toHaveCount(0);
  await page.mouse.move(900, 120);
  await d.caption('Задачи свёрнуты — видны только их названия');
  await d.show(page.locator('[data-tour="rp-gantt"]'));
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('rp-views');
});
