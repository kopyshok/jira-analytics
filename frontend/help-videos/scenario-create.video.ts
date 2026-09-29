// Ролик «Как собрать сценарий квартала»: Сценарии → «Новый сценарий» →
// квартал без сценария + команда → создать → отметить инициативы галочками →
// справа сразу видно нагрузку по ролям.
import { expect, test, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}

/** Первый квартал, для которого у команды ещё нет сценария (не раньше текущего) —
 *  ролик детерминирован в любой день, не зависит от состава демо-базы. */
async function nextFreeQuarter(page: Page, api: string, team: string): Promise<{ year: number; quarter: number }> {
  const res = await page.request.get(`${api}/api/v1/planning/scenarios?teams=${encodeURIComponent(team)}`);
  expect(res.ok()).toBeTruthy();
  const list: ScenarioListItem[] = await res.json();
  const keys = list
    .filter((s) => s.team === team && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  return { year: Math.floor(nextKey / 4), quarter: (nextKey % 4) + 1 };
}

test('scenario-create', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);
  const { year: freeYear, quarter: freeQuarter } = await nextFreeQuarter(page, api, TEAM);

  await d.open('/planning', 'Как собрать сценарий квартала');
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible({ timeout: 15_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('[data-tour="planning-new-scenario"]'), 'Нажмите «Новый сценарий»');

  const modal = page.locator('.ant-modal', { hasText: 'Новый сценарий квартала' });
  await expect(modal).toBeVisible();
  await d.pause(300);

  // «Период» — единственный Form.Item с этим текстом: внутри него один InputNumber
  // (первым в DOM) и один Select (квартал) — команда живёт в отдельном Form.Item ниже.
  const periodItem = modal.locator('.ant-form-item', { hasText: 'Период' });
  const yearInput = periodItem.locator('input').first();
  const quarterSelect = periodItem.locator('.ant-select');

  await d.click(yearInput, 'Укажите год и квартал, где сценария ещё нет');
  await yearInput.press('Control+A');
  await yearInput.pressSequentially(String(freeYear), { delay: 90 });
  await d.pause(400);

  await d.click(quarterSelect, 'Выберите квартал');
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', {
      hasText: new RegExp(`^Q${freeQuarter}$`),
    }),
  );

  const nameInput = modal.locator('#name');
  await d.caption('Название и команда подставились сами');
  await d.show(nameInput);
  await d.pause(1200);

  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Нажмите «Создать»');
  await expect(modal).toBeHidden();

  await expect(page.getByText(`Q${freeQuarter} ${freeYear}`, { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Черновик')).toBeVisible();

  const wrappers = page.locator('[data-flip-wrapper]');
  await expect(wrappers.first()).toBeVisible({ timeout: 15_000 });
  const ids = await wrappers.evaluateAll((els) =>
    els.slice(0, 3).map((el) => el.getAttribute('data-alloc-id')),
  );

  await d.caption('Отметьте галочками 2–3 инициативы квартала');
  for (const id of ids) {
    const row = page.locator(`[data-flip-wrapper][data-alloc-id="${id}"] .backlog-row`);
    await d.click(row);
    await d.pause(500);
  }

  await expect(page.getByText(new RegExp(`включено ${ids.length} из`))).toBeVisible();

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Справа сразу видно нагрузку команды по ролям');
  await d.show(roleCard);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('scenario-create');
});
