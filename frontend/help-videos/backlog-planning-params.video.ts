// Ролик «Как задать параметры планирования»: у задачи утверждённого сценария Q4 —
// шестерёнка → вовлечённость, параллельность, длительность («К Jira»), у длинной
// RFA — таблица «Часы и иерархия», правка плана и история → связь с ресурсным
// планом: меньшая вовлечённость удлиняет фазу после «Распределить».
import { expect, test, type Locator, type Page } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { prepareQuarterPlan, phaseBar, TEAM, type Assignment } from './rp-setup.ts';

type PhaseKey = 'analyst' | 'dev' | 'qa' | 'launch';
const PHASE_LABELS: Record<PhaseKey, string> = {
  analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование (QA)', launch: 'ОПЭ',
};

interface BacklogDetail {
  id: string;
  jira_key: string | null;
  title: string;
  issue_id: string | null;
  has_children_in_backlog: boolean;
  involvement_dev: number | null;
  involvement_dev_jira: number | null;
  duration_analyst_days: number | null;
  duration_analyst_days_jira: number | null;
  duration_dev_days: number | null;
  duration_dev_days_jira: number | null;
  duration_qa_days: number | null;
  duration_qa_days_jira: number | null;
}

interface Ctx {
  api: string;
  rp: string;
  scenarioId: string;
  scenarioLabel: string;
  planId: string;
  item: BacklogDetail;
  assignment: Assignment;
  newInvolvement: number;
  originalInvolvementDev: number | null;
  // «К Jira» показываем на первой попавшейся задаче квартала с заполненным
  // Jira-значением длительности — это не всегда та же задача, что ведёт
  // фазу разработки (в демо-данных это поле заполнено не у всех).
  durationItemId: string | null;
  durationItemKey: string | null;
  durationItemView: 'quarterly' | 'active' | 'archived';
  durationPhase: 'analyst' | 'dev' | 'qa' | null;
  originalDuration: number | null;
}

let ctx: Ctx | null = null;

test.beforeAll(async ({ playwright }, testInfo) => {
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  // prepareQuarterPlan использует только page.request — минимальная заглушка
  // вместо целой страницы (в beforeAll её ещё нет).
  const fakePage = { request } as unknown as Page;
  const { api, rp, scenario, plan, assignments } = await prepareQuarterPlan(fakePage);

  const loadItem = async (id: string): Promise<BacklogDetail> => {
    const res = await request.get(`${api}/backlog/${id}`);
    expect(res.ok()).toBeTruthy();
    return res.json();
  };

  const devAssignments = assignments.filter((a) => a.phase === 'dev' && a.employee_id);
  if (devAssignments.length === 0) throw new Error(`В плане команды ${TEAM} нет фаз разработки`);

  let picked: { item: BacklogDetail; assignment: Assignment } | null = null;
  for (const a of devAssignments) {
    const item = await loadItem(a.backlog_item_id);
    if (item.issue_id && item.has_children_in_backlog) { picked = { item, assignment: a }; break; }
  }
  if (!picked) {
    for (const a of devAssignments) {
      const item = await loadItem(a.backlog_item_id);
      if (item.issue_id) { picked = { item, assignment: a }; break; }
    }
  }
  if (!picked) throw new Error(`В плане команды ${TEAM} нет задач из Jira с фазой разработки`);

  const effective = picked.item.involvement_dev ?? picked.item.involvement_dev_jira ?? 0.8;
  const newInvolvement = Math.max(0.1, Math.round(effective * 0.4 * 20) / 20);

  // Поле «Длительность из Jira» заполнено не у каждой задачи — ищем среди
  // всех задач квартала (не только той, что ведёт фазу разработки).
  type DurationField = 'duration_analyst_days_jira' | 'duration_dev_days_jira' | 'duration_qa_days_jira';
  const phaseByField: Record<DurationField, 'analyst' | 'dev' | 'qa'> = {
    duration_analyst_days_jira: 'analyst', duration_dev_days_jira: 'dev', duration_qa_days_jira: 'qa',
  };
  let durationItemId: string | null = null;
  let durationItemKey: string | null = null;
  let durationPhase: 'analyst' | 'dev' | 'qa' | null = null;
  let originalDuration: number | null = null;
  let durationItemView: 'quarterly' | 'active' | 'archived' = 'quarterly';
  const checkDuration = (it: BacklogDetail) => {
    for (const field of ['duration_analyst_days_jira', 'duration_dev_days_jira', 'duration_qa_days_jira'] as DurationField[]) {
      if (it[field] != null) {
        durationItemId = it.id;
        durationItemKey = it.jira_key;
        durationPhase = phaseByField[field];
        originalDuration = it[field.replace('_jira', '') as 'duration_analyst_days' | 'duration_dev_days' | 'duration_qa_days'];
        return true;
      }
    }
    return false;
  };
  if (!checkDuration(picked.item)) {
    const seen = new Set([picked.item.id]);
    for (const a of assignments) {
      if (seen.has(a.backlog_item_id)) continue;
      seen.add(a.backlog_item_id);
      const it = await loadItem(a.backlog_item_id);
      if (it.issue_id && checkDuration(it)) break;
    }
  }
  // Поле длительности из Jira в демо-данных заполнено не у всех задач квартала —
  // на крайний случай смотрим весь бэклог команды (задача может быть на вкладке
  // «Активные»/«Бэклог»/«Архив»), не только план текущего квартала.
  if (!durationItemId) {
    for (const view of ['quarterly', 'active', 'archived'] as const) {
      const rows: BacklogDetail[] = await (
        await request.get(`${api}/backlog`, { params: { view, teams: TEAM } })
      ).json();
      const hit = rows.find((r) => r.issue_id && checkDuration(r));
      if (hit) { durationItemView = view; break; }
    }
  }

  const quarterNum = Number(String(scenario.quarter).replace('Q', ''));
  expect(
    (await request.put(`${api}/users/me/period`, {
      data: { year: scenario.year, quarter: quarterNum, month: (quarterNum - 1) * 3 + 1 },
    })).ok(),
  ).toBeTruthy();

  ctx = {
    api,
    rp,
    scenarioId: scenario.id,
    scenarioLabel: scenario.name,
    planId: plan.id,
    item: picked.item,
    assignment: picked.assignment,
    newInvolvement,
    originalInvolvementDev: picked.item.involvement_dev,
    durationItemId,
    durationItemView,
    durationItemKey,
    durationPhase,
    originalDuration,
  };
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  if (!ctx) return;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.patch(`${ctx.api}/backlog/${ctx.item.id}`, {
    data: { involvement_dev: ctx.originalInvolvementDev },
  });
  // Правка длительности могла случиться на другой задаче квартала — сбрасываем
  // её отдельно, если это не та же строка (иначе «К Jira» в ролике уже вернул
  // исходное значение сам, но на всякий случай патчим и здесь).
  if (ctx.durationItemId && ctx.durationPhase) {
    await request.patch(`${ctx.api}/backlog/${ctx.durationItemId}`, {
      data: { [`duration_${ctx.durationPhase}_days`]: ctx.originalDuration },
    });
  }
  await request.dispose();
});

test('backlog-planning-params', async ({ page }) => {
  if (!ctx) throw new Error('Данные не подготовлены (beforeAll)');
  const c = ctx;
  const d = new Director(page);
  await d.install();

  // Боковая ссылка «Целевые задачи» ведёт на голый /backlog: по умолчанию
  // открывается вкладка «Активные» — там и лежит задача утверждённого сценария.
  await d.open('/backlog', 'Как задать параметры планирования');
  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Откройте «Целевые задачи»');
  await expect(page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab-active', { hasText: 'Активные' })).toBeVisible();

  const row = pane.locator(`tr[data-row-key="${c.item.id}"]`);
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.scrollIntoViewIfNeeded();

  await d.click(row.locator('[data-tour="backlog-gear"]'), 'У задачи квартала — шестерёнка «Параметры планирования»');
  const modal = page.locator('.ant-modal', { hasText: 'Параметры планирования' });
  await expect(modal).toBeVisible();

  const phaseBlock = (label: string): Locator =>
    modal.getByRole('heading', { name: label, exact: true }).locator('xpath=..');

  const setNumber = async (input: Locator, value: string, caption?: string) => {
    await d.click(input, caption);
    await input.press('Control+A');
    await input.pressSequentially(value, { delay: 90 });
    await input.press('Tab');
    await d.pause(500);
  };

  const devBlock = phaseBlock(PHASE_LABELS.dev);
  await setNumber(
    devBlock.locator('input').nth(0),
    String(c.newInvolvement),
    'Понизьте вовлечённость на фазе разработки',
  );
  await d.caption('Рядом — параллельность: сколько человек ведут фазу одновременно');
  await d.show(devBlock.locator('input').nth(2));
  await d.pause(1200);

  // Показать демонстрацию «К Jira» можно прямо здесь, только если поле
  // длительности из Jira заполнено именно у этой задачи.
  const demoDurationHere = c.durationPhase && c.durationItemId === c.item.id;
  if (demoDurationHere) {
    const durBlock = phaseBlock(PHASE_LABELS[c.durationPhase!]);
    const durInput = durBlock.locator('input').nth(1);
    const jiraBefore = await durInput.inputValue();
    await setNumber(durInput, String(Number(jiraBefore || '0') + 5), 'Длительность тоже можно задать вручную');
    // .last() — на фазе разработки уже может быть своя кнопка «К Jira» у вовлечённости.
    const toJira = durBlock.getByRole('button', { name: 'К Jira' }).last();
    await expect(toJira).toBeVisible();
    await d.click(toJira, 'Кнопка «К Jira» вернёт значение из Jira, если передумали');
    await expect(toJira).toBeHidden();
  }

  await expect(modal.getByText('Часы и иерархия')).toBeVisible({ timeout: 15_000 });
  const hoursTable = modal.locator('table', { hasText: 'Запланировать' });
  await expect(hoursTable).toBeVisible({ timeout: 15_000 });
  await d.caption('Для задачи из Jira здесь видно факт, утверждённые часы и что ещё можно запланировать');
  await d.show(hoursTable);
  await d.pause(2000);

  const editBtn = modal.getByRole('button', { name: '✎ Редактировать план' });
  await d.click(editBtn, 'Плановые часы можно поправить вручную');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();

  const editRow = drawer.locator('tr', { hasText: 'Разработка' });
  const editInput = editRow.locator('input');
  const currentHours = await editInput.inputValue();
  await setNumber(
    editInput,
    String(Math.max(1, Number(currentHours || '0') + 10)),
    'Новое значение — с обязательным комментарием',
  );
  await d.type(drawer.locator('textarea'), 'После сверки часов с руководителем', 'Комментарий — зачем правка');
  await d.click(drawer.getByRole('button', { name: 'Сохранить' }), 'Сохраните');
  await expect(drawer).toBeHidden();

  await d.click(editBtn, 'Откройте правку ещё раз — посмотреть историю');
  await expect(drawer).toBeVisible();
  await d.click(drawer.getByRole('button', { name: /историю/ }), 'Каждая правка остаётся в истории');
  const historyTable = drawer.locator('table').last();
  await expect(historyTable.locator('tbody tr').first()).toBeVisible();
  await d.show(historyTable);
  await d.pause(1800);

  await d.click(drawer.getByRole('button', { name: 'Сбросить к Jira' }), 'Сбросьте правку — часы снова из Jira');
  await expect(drawer).toBeHidden();

  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните параметры');
  await expect(modal).toBeHidden();

  // Длительность из Jira заполнена у другой задачи — заходим к ней отдельно,
  // только чтобы показать «К Jira»; сохранять здесь нечего. Задача может быть
  // на другой вкладке (не обязательно «Активные»).
  if (c.durationPhase && c.durationItemId && c.durationItemId !== c.item.id) {
    if (c.durationItemView !== 'quarterly') {
      const tabLabel = c.durationItemView === 'active' ? 'Бэклог' : 'Архив';
      await d.click(page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: tabLabel }));
    }
    const otherRow = pane.locator(`tr[data-row-key="${c.durationItemId}"]`);
    await expect(otherRow).toBeVisible({ timeout: 15_000 });
    await otherRow.scrollIntoViewIfNeeded();
    await d.click(otherRow.locator('[data-tour="backlog-gear"]'), 'У другой задачи заполнена длительность из Jira');
    const otherModal = page.locator('.ant-modal', { hasText: 'Параметры планирования' });
    await expect(otherModal).toBeVisible();
    const otherPhaseBlock = otherModal.getByRole('heading', { name: PHASE_LABELS[c.durationPhase], exact: true }).locator('xpath=..');
    const otherDurInput = otherPhaseBlock.locator('input').nth(1);
    const otherJiraBefore = await otherDurInput.inputValue();
    await setNumber(otherDurInput, String(Number(otherJiraBefore || '0') + 5), 'Длительность тоже можно задать вручную');
    const otherToJira = otherPhaseBlock.getByRole('button', { name: 'К Jira' });
    await expect(otherToJira).toBeVisible();
    await d.click(otherToJira, 'Кнопка «К Jira» вернёт значение из Jira, если передумали');
    await expect(otherToJira).toBeHidden();
    await d.click(otherModal.locator('.ant-modal-close'), 'Ничего менять не нужно — просто закройте окно');
    await expect(otherModal).toBeHidden();
  }

  await d.click(page.locator('.side-item', { hasText: 'Ресурс. планир.' }), 'Перейдите в «Ресурс. планир.»');
  const select = page.locator('[data-tour="rp-scenario-select"]');
  await expect(select).toBeVisible();
  await d.click(select);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: c.scenarioLabel }));
  await expect(page.locator('[data-tour="rp-gantt"]')).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(900, 120);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });

  const gantt = await (await page.request.get(`${c.rp}/resource-plans/${c.planId}/gantt`)).json() as {
    assignments: Assignment[];
  };
  const updated = gantt.assignments.find(
    (a) => a.backlog_item_id === c.assignment.backlog_item_id && a.phase === 'dev' && a.part_number === c.assignment.part_number,
  );
  if (!updated?.end_date || !c.assignment.end_date) throw new Error('Не удалось найти фазу разработки после пересчёта');
  expect(dayjs(updated.end_date).isAfter(dayjs(c.assignment.end_date))).toBeTruthy();

  const bar = phaseBar(page, updated);
  await bar.scrollIntoViewIfNeeded();
  await page.mouse.move(900, 120);
  await d.caption('Вовлечённость из целевой задачи изменила длительность фазы');
  await d.show(bar);
  await d.pause(2000);

  await d.caption('Готово', 2200);
  await d.save('backlog-planning-params');
});
