// Ролик «Как сменить исполнителя фазы»: полоса фазы → карточка → «Сотрудник» →
// группы и загрузка в списке → новый человек из команды → предупреждение о
// конфликтах → «Всё равно сохранить и пересчитать» → фаза у нового исполнителя.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { type Assignment, phaseBar, prepareQuarterPlan } from './rp-setup.ts';

type Candidate = { employee_id: string; display_name: string; role: string | null };
type CandidateGroup = { key: string; label: string; employees: Candidate[] };
type Preview = { has_conflicts: boolean };

test('rp-executor', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const { rp, plan, assignments } = await prepareQuarterPlan(page);
  const url = (a: Assignment, tail: string) => `${rp}/resource-plans/${plan.id}/assignments/${a.id}/${tail}`;

  // Самый ранний анализ, у которого в своей команде есть другой человек той же
  // специализации (не разработчик), при выборе которого сервис предупредит о
  // конфликте — так в ролике всегда видно окно с предупреждением.
  let phase: Assignment | undefined;
  let next: Candidate | undefined;
  const analyses = assignments
    .filter((a) => a.phase === 'analyst' && a.employee_id && a.start_date)
    .sort((a, b) => a.start_date!.localeCompare(b.start_date!));
  for (const a of analyses) {
    const groups: CandidateGroup[] = await (await page.request.get(url(a, 'candidates'))).json();
    const team = groups.find((g) => g.key === 'team')?.employees ?? [];
    for (const e of team.filter((c) => c.employee_id !== a.employee_id && c.role?.toLowerCase() !== 'dev')) {
      const preview: Preview = await (
        await page.request.post(url(a, 'preview-employee-change'), { data: { employee_id: e.employee_id } })
      ).json();
      if (preview.has_conflicts) {
        next = e;
        break;
      }
    }
    if (next) {
      phase = a;
      break;
    }
  }
  if (!phase || !next) throw new Error('Нет анализа, где смена исполнителя даёт предупреждение о конфликте');

  const bar = phaseBar(page, phase);
  const row = page.locator('[data-gantt-row="true"]').filter({ has: bar });

  await d.open(`/resource-planning?plan_id=${plan.id}`, 'Как сменить исполнителя фазы');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible();
  await expect(bar).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(bar, 'Нажмите на полосу фазы');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const field = (label: string) =>
    drawer
      .locator('.ant-descriptions-row')
      .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: new RegExp(`^${label}$`) }) });
  const employee = field('Сотрудник');

  await d.click(employee.locator('.ant-select'), 'В поле «Сотрудник» откройте список');
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown.locator('.ant-select-item-group', { hasText: 'Моя команда' })).toBeVisible();
  const option = dropdown.locator('.ant-select-item-option', { hasText: next.display_name });
  await expect(option).toBeVisible();
  await d.caption('Люди сгруппированы: из Jira, своя команда, другие команды');
  await d.show(dropdown.locator('.rc-virtual-list'));
  await d.pause(1400);
  await d.caption('У каждого видна загрузка за квартал');
  await d.show(option);
  await d.pause(1200);

  await d.click(option, 'Выберите нового исполнителя');
  const modal = page.getByRole('dialog', { name: /Конфликты/ });
  await expect(modal).toBeVisible();
  await d.caption('Сервис предупредит об отпуске или перегрузке');
  await d.show(modal.locator('.ant-modal-body'));
  await d.pause(1600);

  await d.click(modal.getByRole('button', { name: 'Всё равно сохранить и пересчитать' }), 'Нажмите «Всё равно сохранить и пересчитать»');
  await expect(modal).toBeHidden();

  // Фаза закреплена за новым исполнителем, план пересчитан.
  const pinned = drawer.locator('.ant-drawer-header .ant-tag', { hasText: 'Закреплено' });
  await expect(pinned).toBeVisible();
  await expect(employee.locator('.ant-select')).toContainText(next.display_name);
  const after: { assignments: (Assignment & { pinned_employee: boolean })[] } = await (
    await page.request.get(`${rp}/resource-plans/${plan.id}/gantt`)
  ).json();
  const moved = after.assignments.find(
    (a) => a.backlog_item_id === phase.backlog_item_id && a.phase === phase.phase && a.part_number === phase.part_number,
  );
  expect(moved?.employee_id).toBe(next.employee_id);
  expect(moved?.pinned_employee).toBeTruthy();

  await d.caption('Исполнитель закреплён, план пересчитан');
  await d.show(employee);
  await d.pause(1200);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();
  // Настоящая мышь осталась над диаграммой — уводим, чтобы не подсвечивались полосы.
  await page.mouse.move(900, 120);

  const name = row.getByText(next.display_name, { exact: true });
  await expect(name).toBeVisible();
  await expect(bar).toBeVisible();
  await d.caption('Фаза перешла к новому исполнителю');
  await d.show(name, bar);
  await d.pause(2000);

  await d.caption('Готово', 2200);
  await d.save('rp-executor');
});
