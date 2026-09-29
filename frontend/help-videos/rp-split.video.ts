// Ролик «Как разбить фазу на двоих»: карточка разработки → «Разбить на части»
// (60/40, пропорционально) → второй части — другой «Сотрудник» → «Распределить» →
// на диаграмме две отдельные полосы, каждая у своего человека. По пути
// показаны поле «Предшественники», «Слить части в одну» и «Снять все ручные правки».
import { expect, type Locator, test } from '@playwright/test';
import type { AssignmentOut } from '../src/api/resourcePlanning.ts';
import { Director } from './director.ts';
import { type Assignment, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

type Phase = Assignment & { hours_allocated: number | null };
type Candidate = { employee_id: string; display_name: string; role: string | null };
type CandidateGroup = { key: string; label: string; employees: Candidate[] };
type Preview = { has_conflicts: boolean };

test('rp-split', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Самая ранняя разработка с исполнителем и целыми часами, у которой есть
  // свой анализ — он пригодится как общий предшественник для обеих частей.
  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  const phases = assignments as Phase[];
  const dev = phases
    .filter((a) => a.phase === 'dev' && a.part_number === 1 && a.employee_id && a.start_date)
    .filter((a) => Number.isInteger(a.hours_allocated) && (a.hours_allocated ?? 0) >= 16)
    .filter((a) => phases.some((p) => p.phase === 'analyst' && p.backlog_item_id === a.backlog_item_id))
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!))[0];
  if (!dev) throw new Error('В плане нет разработки с анализом и целыми часами');
  const total = dev.hours_allocated!;
  const first = Math.round(total * 0.6);
  const second = total - first;

  const url = (tail: string) => `${rp}/resource-plans/${plan.id}/${tail}`;
  const status = (text: string) => page.locator('.ant-tag', { hasText: new RegExp(`^${text}$`) });
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  const field = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) });

  /** Выделить число в поле и набрать новое с видимой скоростью. */
  const retype = async (fieldLoc: Locator, value: number, caption?: string) => {
    await d.click(fieldLoc, caption);
    await fieldLoc.press('ControlOrMeta+A');
    await fieldLoc.pressSequentially(String(value), { delay: 90 });
    await d.pause(500);
  };

  const part1 = phaseBar(page, dev);
  const part2 = phaseBar(page, { ...dev, part_number: 2 });

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как разбить фазу на двоих');
  await expect(status('Готово')).toBeVisible();
  await expect(part1).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(part1, 'Нажмите на полосу разработки');
  await expect(drawer).toBeVisible();
  await d.click(drawer.getByRole('button', { name: 'Разбить на части' }), 'В карточке нажмите «Разбить на части»');

  const modal = page.getByRole('dialog', { name: 'Разбить фазу на части' });
  await expect(modal).toBeVisible();
  const hours = modal.getByRole('spinbutton');
  await expect(hours).toHaveCount(2);
  await retype(hours.nth(0), first, 'Разделите часы, например 60/40');
  await retype(hours.nth(1), second);
  const sum = modal.getByText(/^Сумма:/);
  await expect(sum).toHaveText(`Сумма: ${total} ч (требуется ${total} ч)`);
  await d.caption('Вместе части дают все часы фазы');
  await d.show(sum);
  await d.pause(900);

  const cascade = modal.getByRole('checkbox');
  await expect(cascade).toBeChecked();
  await d.caption('Галочка — следующие фазы разделятся в той же пропорции');
  await d.show(modal.getByText('Разбить и последующие фазы пропорционально'));
  await d.pause(1000);

  await d.click(modal.getByRole('button', { name: 'Разбить', exact: true }), 'Нажмите «Разбить»');
  await expect(modal).toBeHidden();

  // Карточка осталась открытой — теперь в ней первая часть и кнопка слияния.
  const merge = drawer.getByRole('button', { name: 'Слить части в одну' });
  await expect(merge).toBeVisible();
  await d.caption('Передумали — «Слить части в одну» вернёт фазу целиком');
  await d.show(merge);
  await d.pause(1800);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  await expect(part1).toBeVisible();
  await expect(part2).toBeVisible();
  await d.caption('Части пока идут одна за другой — второй займётся другой человек');
  await d.show(part1, part2);
  await d.pause(1400);

  const qaBars = page.locator(`[data-testid^="rp-bar-${dev.backlog_item_id}-qa-"]`);
  if ((await qaBars.count()) === 2) {
    await d.caption('Галочка сработала и на тестировании — оно тоже разделилось');
    await d.show(qaBars.first(), qaBars.last());
    await d.pause(1600);
  }

  // Реальный id второй части после разбивки — понадобится для подбора коллеги.
  const afterSplit: { assignments: Phase[] } = await (await page.request.get(url('gantt'))).json();
  const part2Row = afterSplit.assignments.find(
    (a) => a.backlog_item_id === dev.backlog_item_id && a.phase === 'dev' && a.part_number === 2,
  );
  if (!part2Row) throw new Error('Вторая часть не найдена после разбивки');

  // Коллега той же роли без конфликтов — чтобы не отвлекаться на окно «Конфликты».
  const groups: CandidateGroup[] = await (
    await page.request.get(url(`assignments/${part2Row.id}/candidates`))
  ).json();
  const team = (groups.find((g) => g.key === 'team')?.employees ?? []).filter(
    (c) => c.employee_id !== part2Row.employee_id,
  );
  let peer: Candidate | undefined;
  for (const c of team) {
    const preview: Preview = await (
      await page.request.post(url(`assignments/${part2Row.id}/preview-employee-change`), {
        data: { employee_id: c.employee_id },
      })
    ).json();
    if (!preview.has_conflicts) {
      peer = c;
      break;
    }
  }
  if (!peer) throw new Error('Нет коллеги без конфликтов для второй части');

  await d.click(part2, 'Откройте вторую часть');
  await expect(drawer).toBeVisible();
  const employee = field('Сотрудник');
  await d.click(employee.locator('.ant-select'), 'В поле «Сотрудник» выберите другого человека');
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: peer.display_name }),
  );
  await expect(employee.locator('.ant-select')).toContainText(peer.display_name);

  const predecessors = field('Предшественники');
  await d.caption('«Предшественники» — от какой фазы зависит начало этой части');
  await d.show(predecessors);
  await d.pause(1900);

  const resetAll = drawer.getByRole('button', { name: 'Снять все ручные правки' });
  await expect(resetAll).toBeVisible();
  await d.caption('Здесь же можно снять все правки этой фазы разом');
  await d.show(resetAll);
  await d.pause(1900);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  await page.mouse.move(900, 120);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await expect(status('Готово')).toBeVisible({ timeout: 60_000 });

  const final: { assignments: (Phase & { predecessor_ids?: string[] })[] } = await (
    await page.request.get(url('gantt'))
  ).json();
  const p1 = final.assignments.find(
    (a) => a.backlog_item_id === dev.backlog_item_id && a.phase === 'dev' && a.part_number === 1,
  ) as AssignmentOut;
  const p2 = final.assignments.find(
    (a) => a.backlog_item_id === dev.backlog_item_id && a.phase === 'dev' && a.part_number === 2,
  ) as AssignmentOut;
  expect(p2.employee_id).toBe(peer.employee_id);
  expect(p1.start_date && p1.end_date && p2.start_date && p2.end_date).toBeTruthy();

  await expect(part1).toBeVisible();
  await expect(part2).toBeVisible();
  await page.mouse.move(900, 120);
  await d.caption('План пересчитан — на диаграмме две части фазы');
  await d.show(part1, part2);
  await d.pause(1400);
  await d.caption(`Часть 1 — ${dev.employee_name}, часть 2 — ${peer.display_name}`);
  await d.show(part1, part2);
  await d.pause(2400);

  await d.caption('Готово', 2200);
  await d.save('rp-split');
});
