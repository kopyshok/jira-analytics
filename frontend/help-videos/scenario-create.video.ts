// Ролик «Как собрать сценарий квартала»: «Новый сценарий» на свободный квартал
// (название и команда подставились) → «Правила» → копия правил прошлого
// квартала → «Распределение»: галочки, «На бэклог» тает, дефицит по роли
// появляется и уходит, приоритет, «поднимать наверх», переименование.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}

interface ApprovedScenario {
  id: string;
  name: string;
  team: string | null;
  year: number | null;
  quarter: string | null;
}

interface AllocLite {
  id: string;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
}

const totalHrs = (a: AllocLite): number =>
  (a.estimate_analyst_hours ?? 0) + (a.estimate_dev_hours ?? 0) + (a.estimate_qa_hours ?? 0);

let freeYear = 0;
let freeQuarter = 0;
let sourceScenario: ApprovedScenario | null = null;
// Заполняется внутри теста (сценарий создаётся на камеру) — id нужен только
// для очистки в afterAll.
let createdScenarioId: string | null = null;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Первый квартал, для которого у команды ещё нет сценария (не раньше текущего) —
  // подготовка детерминирована в любой день и не зависит от состава демо-базы.
  const scenariosRes = await request.get(`${api}/planning/scenarios`, { params: { teams: TEAM } });
  expect(scenariosRes.ok()).toBeTruthy();
  const list: ScenarioListItem[] = await scenariosRes.json();
  const keys = list
    .filter((s) => s.team === TEAM && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  freeYear = Math.floor(nextKey / 4);
  freeQuarter = (nextKey % 4) + 1;

  // Утверждённый сценарий команды прошлого квартала — источник для «Из сценария».
  const approvedRes = await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } });
  expect(approvedRes.ok()).toBeTruthy();
  const approved: ApprovedScenario[] = await approvedRes.json();
  const withPeriod = approved.filter((s) => s.team === TEAM && s.year != null && s.quarter != null);
  expect(withPeriod.length, `нет утверждённых сценариев команды ${TEAM}`).toBeGreaterThan(0);
  sourceScenario = withPeriod.sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`)).at(-1)!;

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (createdScenarioId) {
    await request.delete(`${api}/planning/scenarios/${createdScenarioId}`);
  }
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('scenario-create', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/planning', 'Как собрать сценарий квартала');
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible({ timeout: 15_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  // === Создание сценария на свободный квартал ===
  await d.click(page.locator('[data-tour="planning-new-scenario"]'), 'Нажмите «Новый сценарий»');

  const modal = page.locator('.ant-modal', { hasText: 'Новый сценарий квартала' });
  await expect(modal).toBeVisible();
  await d.pause(300);

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
  const teamField = modal.locator('.ant-form-item', { hasText: 'Команда' });
  await d.caption('Название и команда подставились сами');
  await d.show(nameInput, teamField);
  await d.pause(1200);

  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Нажмите «Создать»');
  await expect(modal).toBeHidden();

  await expect(page.getByText(`Q${freeQuarter} ${freeYear}`, { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText('Черновик')).toBeVisible();

  const createdUrl = new URL(page.url());
  createdScenarioId = createdUrl.searchParams.get('scenario');
  expect(createdScenarioId, 'не удалось определить id созданного сценария').toBeTruthy();
  const api = String(test.info().config.metadata.backendUrl);

  // === Правила: скопировать из прошлого утверждённого сценария ===
  await d.click(page.locator('[data-tour="planning-tab-rules"]'), 'Откройте вкладку «Правила»');
  const rulesCard = page.locator('[data-tour="planning-rules-card"]');
  await expect(rulesCard).toBeVisible();

  await d.click(rulesCard.getByRole('button', { name: 'Из сценария' }), 'Скопируйте правила прошлого квартала');
  const popover = page.locator('.ant-popover:visible', { hasText: 'Скопировать правила из сценария' });
  await expect(popover).toBeVisible();
  await d.click(popover.locator('.ant-select'));
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: sourceScenario!.name }),
  );
  await d.click(popover.getByRole('button', { name: 'Скопировать' }));
  await expect(page.getByText(/Скопировано правил/)).toBeVisible({ timeout: 10_000 });

  await d.caption('Правила скопированы — они сразу уменьшают «На бэклог»');
  await d.show(rulesCard);
  await d.pause(1400);

  // === Распределение: галочки, «На бэклог», дефицит ===
  await d.click(page.locator('[data-tour="planning-tab-distribution"]'), 'Вернитесь на вкладку «Распределение»');

  const allocsRes = await page.request.get(`${api}/api/v1/planning/scenarios/${createdScenarioId}/allocations`);
  expect(allocsRes.ok()).toBeTruthy();
  const allocs: AllocLite[] = await allocsRes.json();
  // По возрастанию часов: дефицит (если вообще случится) набежит постепенно,
  // от нескольких задач, а не от одной огромной — тогда снятие последней
  // гарантированно вернёт баланс, а не оставит дефицит от первой же строки.
  const byHoursAsc = [...allocs].filter((a) => totalHrs(a) > 0).sort((a, b) => totalHrs(a) - totalHrs(b));
  expect(byHoursAsc.length, 'в бэклоге нет задач с часами').toBeGreaterThan(0);

  const badge = page.locator('[data-testid="scenario-deficit-badge"]');
  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  // «На бэклог» рисуется дважды (свёрнутый и развёрнутый варианты лежат в DOM
  // одновременно) — берём тот, что сейчас показан.
  const resourceRow = page.locator('div[aria-hidden="false"]', { hasText: 'На бэклог' }).first();

  await d.caption('Отмечайте галочками задачи квартала');
  // Клик по центру всей широкой строки (.backlog-row) иногда попадает не по
  // пустому месту, а по ячейке «Аналитик»/«Разработчик» — те гасят всплытие
  // клика к строке и открывают свой список вместо переключения галочки.
  // Кликаем прицельно по самой галочке — там нет такой ловушки.
  const checkedIds: string[] = [];
  for (const a of byHoursAsc.slice(0, 10)) {
    const row = page.locator(`[data-flip-wrapper][data-alloc-id="${a.id}"] .backlog-row`);
    const checkbox = row.locator('.ant-checkbox');
    await d.click(checkbox);
    await expect(row.locator('input[type="checkbox"]')).toBeChecked({ timeout: 5_000 });
    checkedIds.push(a.id);
    await d.pause(400);
    // Останавливаемся не раньше второй отмеченной задачи — иначе демонстрация
    // снятия дефицита оставит список пустым.
    if (checkedIds.length >= 2 && (await badge.isVisible())) break;
  }
  expect(checkedIds.length, 'ни одна задача не была отмечена').toBeGreaterThan(0);

  await d.caption('«На бэклог» тает по мере включения задач');
  await d.show(resourceRow);
  await d.pause(1400);

  await d.caption('Справа сразу видно нагрузку команды по ролям');
  await d.show(roleCard);
  await d.pause(1400);

  if (await badge.isVisible()) {
    await d.caption('Роли не хватает часов — появился бейдж дефицита');
    await d.show(badge);
    await d.pause(1600);

    // Снимаем задачи с конца, пока дефицит не исчезнет — но хотя бы одну
    // оставляем отмеченной для дальнейшей демонстрации приоритета.
    let firstRemoval = true;
    while ((await badge.isVisible()) && checkedIds.length > 1) {
      const id = checkedIds[checkedIds.length - 1];
      const row = page.locator(`[data-flip-wrapper][data-alloc-id="${id}"] .backlog-row`);
      await d.click(row.locator('.ant-checkbox'), firstRemoval ? 'Снимите задачу — дефицит уходит' : undefined);
      await expect(row.locator('input[type="checkbox"]')).not.toBeChecked({ timeout: 5_000 });
      checkedIds.pop();
      firstRemoval = false;
      await d.pause(500);
    }
    await d.pause(600);
  }
  expect(checkedIds.length, 'не осталось отмеченных задач').toBeGreaterThan(0);

  // === Приоритет ===
  const includedRow = page.locator(`[data-flip-wrapper][data-alloc-id="${checkedIds[0]}"] .backlog-row`);
  const priorityInput = includedRow.locator('.backlog-priority-input input');
  await d.click(priorityInput, 'Поменяйте приоритет задачи');
  await priorityInput.press('Control+A');
  await priorityInput.pressSequentially('1', { delay: 90 });
  await priorityInput.press('Tab');
  await d.pause(500);

  // === «поднимать наверх» ===
  await d.click(
    page.locator('[data-tour="planning-lift-toggle"] .ant-switch'),
    '«поднимать наверх» — иначе включённая задача остаётся на месте',
  );
  await d.pause(800);

  // === Переименование ===
  const nameWrap = page.locator('[data-tour="planning-scenario-name"]');
  await d.click(nameWrap.locator('.ant-typography-edit'), 'Переименуйте сценарий');
  const editArea = page.locator('.ant-typography-edit-content textarea');
  await expect(editArea).toBeFocused();
  await editArea.press('Control+A');
  await editArea.pressSequentially('Итоговый вариант квартала', { delay: 70 });
  await editArea.press('Enter');
  await expect(page.getByText('Итоговый вариант квартала', { exact: true })).toBeVisible();
  await d.pause(600);

  await d.caption('Готово', 2200);
  await d.save('scenario-create');
});
