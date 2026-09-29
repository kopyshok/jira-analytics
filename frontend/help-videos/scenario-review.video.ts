// Ролик «Как пересмотреть сценарий в середине квартала»: у утверждённого
// сценария новый отпуск сотрудника (заведён через «Ресурсы») показывает полосу
// «Доступность изменилась» → «Пересмотреть сценарий» → переоценка переходящей
// задачи → «Утвердить» снова (новая ревизия) → «История» (состав и доступность
// по ревизиям) → «Сравнить» с другим сценарием → «Экспорт». В конце сценарий
// остаётся утверждён, отпуск убран.
// Кнопку «Diff» сознательно не показываем: она сравнивает черновик с первым по
// алфавиту утверждённым сценарием КВАРТАЛА (а не команды) — у демо-базы это
// сценарий другой команды, и в кадре мелькнули бы чужие задачи. Так и задумано
// в сервисе (см. docs/help/planning.md, «Diff» показывает много изменений...),
// но для ролика это путаница, а не то, что мы объясняем.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

// Категория ворклога → роль (подмножество app/services/continuation_service.py
// CATEGORY_TO_ROLE — только чтобы найти задачу, куда можно положить «прошлое»
// списание для фабрикации метки «⚠ продолжение», см. ниже.
const CATEGORY_TO_ROLE: Record<string, 'analyst' | 'dev' | 'qa'> = {
  analysis: 'analyst',
  business_analysis: 'analyst',
  consult: 'analyst',
  support_consultation: 'analyst',
  development: 'dev',
  tech_debt: 'dev',
  testing: 'qa',
};

/** Путь к одноразовой копии базы этого прогона — та же, что открывает бэкенд. */
function runDbPath(): string {
  const port = process.env.VIDEOS_BACKEND_PORT ?? '8012';
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

interface ScenarioItem {
  id: string;
  name: string;
  year: number | null;
  quarter: string | null;
  team: string | null;
  status: 'draft' | 'approved';
}

interface AllocationItem {
  id: string;
  included: boolean;
  override_estimate_analyst_hours: number | null;
  override_estimate_dev_hours: number | null;
  override_estimate_qa_hours: number | null;
  override_estimate_opo_hours: number | null;
}

interface ContinuationRow {
  is_continuation: boolean;
  jira_estimate: { analyst: number; dev: number; qa: number; opo: number };
}

interface Employee {
  employee_id: string;
  display_name: string;
}

interface AbsenceReason {
  id: string;
  label: string;
  is_planned: boolean;
}

interface Absence {
  id: string;
  employee_id: string;
  start_date: string;
  end_date: string;
}

const ROLE_LABEL: Record<'analyst' | 'dev' | 'qa', string> = {
  analyst: 'Аналитика',
  dev: 'Разработка',
  qa: 'Тестирование',
};

let scenarioId = '';
let allocId = '';
let roleLabel = '';
let absenceEmployeeName = '';
let absenceId = '';
let compareScenarioName: string | null = null;
let fabricatedWorklogId: string | null = null;
let fabricatedCategoryIssueId: string | null = null;
let fabricatedCategoryOriginal: string | null = null;

// Данные готовим до открытия окна — запись идёт с момента создания страницы.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string): Promise<T> => {
    const res = await request.get(url);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  const scenarios = await getJson<ScenarioItem[]>(
    `${api}/planning/scenarios?teams=${encodeURIComponent(TEAM)}`,
  );
  const scenario = scenarios.find((s) => s.team === TEAM && s.year === 2026 && s.quarter === 'Q4');
  expect(scenario, `нет сценария Q4 2026 команды ${TEAM}`).toBeTruthy();
  scenarioId = scenario!.id;
  if (scenario!.status !== 'approved') {
    const res = await request.post(`${api}/planning/scenarios/${scenarioId}/approve`);
    expect(res.ok()).toBeTruthy();
  }

  // Второй сценарий для кнопки «Сравнить» — предыдущий квартал той же команды,
  // а если его нет, любой другой утверждённый сценарий команды.
  const compareCandidate =
    scenarios.find(
      (s) => s.team === TEAM && s.id !== scenarioId && s.status === 'approved' && s.year === 2026 &&
        (s.quarter === 'Q3' || s.quarter === 'Q2'),
    ) ?? scenarios.find((s) => s.team === TEAM && s.id !== scenarioId && s.status === 'approved');
  compareScenarioName = compareCandidate?.name ?? null;

  // Строка с меткой «⚠ продолжение», ещё без переоценки — её и переоценим в ролике.
  const [allocs, continuationFirst] = await Promise.all([
    getJson<AllocationItem[]>(`${api}/planning/scenarios/${scenarioId}/allocations`),
    getJson<{ info_by_allocation_id: Record<string, ContinuationRow> }>(
      `${api}/planning/scenarios/${scenarioId}/continuation-info`,
    ),
  ]);
  let continuation = continuationFirst;
  let target = allocs.find((a) => {
    const info = continuation.info_by_allocation_id[a.id];
    return (
      a.included &&
      info?.is_continuation &&
      a.override_estimate_analyst_hours == null &&
      a.override_estimate_dev_hours == null &&
      a.override_estimate_qa_hours == null &&
      a.override_estimate_opo_hours == null
    );
  });

  // Демо-квартал ещё не наступил (сегодня раньше его начала) — списаний из
  // прошлого у задач нет вовсе, метка «⚠ продолжение» не появится ни у одной
  // строки. Заводим её сами: списание за пределами квартала на задачу без
  // переоценки (таблицы ворклогов нет в публичном API — пишем прямо в
  // одноразовую копию базы этого прогона, как это делает prepare-db.ts).
  // Категория задачи — по ней определяется роль списания — у корневых
  // инициатив стоит «Квартальные задачи», а не вид работ; чтобы списание
  // засчиталось, временно ставим корню вид работ «Разработка» и возвращаем
  // исходное значение в afterAll.
  if (!target) {
    const db = new DatabaseSync(runDbPath());
    db.exec('PRAGMA busy_timeout=5000');
    try {
      const rows = db
        .prepare(
          `SELECT sa.id AS alloc_id, i.id AS issue_id, i.assigned_category AS category
           FROM scenario_allocations sa
           JOIN backlog_items bi ON bi.id = sa.backlog_item_id
           JOIN issues i ON i.id = bi.issue_id
           WHERE sa.scenario_id = ? AND sa.included_flag = 1`,
        )
        .all(scenarioId) as { alloc_id: string; issue_id: string; category: string | null }[];
      let candidate = rows.find((r) => r.category && CATEGORY_TO_ROLE[r.category]);
      if (!candidate) {
        candidate = rows[0];
        expect(candidate, 'у сценария нет включённых строк со своей задачей').toBeTruthy();
        fabricatedCategoryIssueId = candidate!.issue_id;
        fabricatedCategoryOriginal = candidate!.category;
        db.prepare('UPDATE issues SET assigned_category = ? WHERE id = ?').run(
          'development',
          fabricatedCategoryIssueId,
        );
      }
      const employeeRow = db.prepare('SELECT id FROM employees LIMIT 1').get() as { id: string };
      const now = new Date().toISOString().replace('T', ' ').replace('Z', '');
      fabricatedWorklogId = `help-video-${candidate!.alloc_id}`;
      db.prepare(
        `INSERT INTO worklogs
           (id, jira_worklog_id, started_at, hours, time_spent_seconds, issue_id, employee_id, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      ).run(
        fabricatedWorklogId,
        `help-video-scenario-review-${candidate!.alloc_id}`,
        '2026-09-20 10:00:00',
        8,
        28_800,
        candidate!.issue_id,
        employeeRow.id,
        now,
        now,
      );
    } finally {
      db.close();
    }

    continuation = await getJson<{ info_by_allocation_id: Record<string, ContinuationRow> }>(
      `${api}/planning/scenarios/${scenarioId}/continuation-info`,
    );
    target = allocs.find((a) => continuation.info_by_allocation_id[a.id]?.is_continuation);
  }

  expect(target, 'нет переходящей задачи без переоценки').toBeTruthy();
  allocId = target!.id;
  const jira = continuation.info_by_allocation_id[allocId].jira_estimate;
  const roleKey = (['dev', 'analyst', 'qa'] as const).find((r) => (jira[r] ?? 0) > 0) ?? 'analyst';
  roleLabel = ROLE_LABEL[roleKey];

  // Отпуск сотруднику команды — появится полоса «Доступность изменилась».
  const resource = await getJson<{ employees: Employee[] }>(
    `${api}/planning/scenarios/${scenarioId}/resource`,
  );
  const reasons = await getJson<AbsenceReason[]>(`${api}/capacity/absence-reasons`);
  const reason = reasons.find((r) => r.label === 'Отпуск' && r.is_planned);
  expect(reason, 'в справочнике нет причины «Отпуск»').toBeTruthy();

  const candidateWindows: [string, string][] = [
    ['2026-11-09', '2026-11-13'],
    ['2026-11-23', '2026-11-27'],
    ['2026-12-07', '2026-12-11'],
    ['2026-10-19', '2026-10-23'],
  ];
  let picked: Employee | null = null;
  let pickedWindow: [string, string] | null = null;
  for (const emp of resource.employees) {
    const existing = await getJson<Absence[]>(`${api}/capacity/absences?employee_id=${emp.employee_id}`);
    const free = candidateWindows.find(([s, e]) => !existing.some((a) => a.start_date <= e && a.end_date >= s));
    if (free) {
      picked = emp;
      pickedWindow = free;
      break;
    }
  }
  expect(picked && pickedWindow, 'не нашлось свободного окна для отпуска').toBeTruthy();
  absenceEmployeeName = picked!.display_name;

  const created = await request.post(`${api}/capacity/absences`, {
    data: {
      employee_id: picked!.employee_id,
      start_date: pickedWindow![0],
      end_date: pickedWindow![1],
      reason_id: reason!.id,
    },
  });
  expect(created.ok()).toBeTruthy();
  const absence = (await created.json()) as Absence;
  absenceId = absence.id;

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (absenceId) await request.delete(`${api}/capacity/absences/${absenceId}`);
  if (fabricatedWorklogId || fabricatedCategoryIssueId) {
    const db = new DatabaseSync(runDbPath());
    db.exec('PRAGMA busy_timeout=5000');
    try {
      if (fabricatedWorklogId) db.prepare('DELETE FROM worklogs WHERE id = ?').run(fabricatedWorklogId);
      if (fabricatedCategoryIssueId) {
        db.prepare('UPDATE issues SET assigned_category = ? WHERE id = ?').run(
          fabricatedCategoryOriginal,
          fabricatedCategoryIssueId,
        );
      }
    } finally {
      db.close();
    }
  }
  if (scenarioId) {
    const res = await request.get(`${api}/planning/scenarios/${scenarioId}`);
    if (res.ok()) {
      const s = (await res.json()) as { status: string };
      if (s.status !== 'approved') await request.post(`${api}/planning/scenarios/${scenarioId}/approve`);
    }
  }
  await request.dispose();
});

test('scenario-review', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, 'Как пересмотреть сценарий в середине квартала');

  const driftText = page.locator('span', { hasText: /Доступность изменилась/ });
  await expect(driftText).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1200);

  await d.click(driftText, 'Появилась полоса «Доступность изменилась»');
  const addedLine = page.getByText(/Добавлено:/).first();
  await expect(addedLine).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(absenceEmployeeName).first()).toBeVisible();
  await d.caption('Отпуск из «Ресурсов» изменил доступность команды');
  await d.show(addedLine);
  await d.pause(1800);

  await d.click(page.getByRole('button', { name: 'Пересмотреть сценарий' }), 'Нажмите «Пересмотреть сценарий»');
  await expect(page.locator('.ant-badge-status-text', { hasText: 'Черновик' })).toBeVisible({ timeout: 15_000 });
  await d.pause(600);

  const row = page.locator(`[data-flip-wrapper][data-alloc-id="${allocId}"]`);
  await expect(row).toBeVisible();
  await row.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(600);

  const contTag = row.locator('.ant-tag', { hasText: '⚠ продолжение' });
  await expect(contTag).toBeVisible();
  await d.caption('У переходящей задачи — метка «⚠ продолжение»: пора переоценить остаток');
  await d.show(contTag);
  await d.pause(1400);

  await d.click(row.getByTitle('Переоценить план квартала'), 'Нажмите на карандаш рядом с названием');
  const popover = page.locator('.ant-popover', { hasText: 'Оригинал Jira' });
  await expect(popover).toBeVisible();
  await d.caption('Видно, сколько уже списано в прошлых периодах');
  await d.show(popover.getByText(/Списано в прошлых периодах/));
  await d.pause(1600);

  const roleRow = popover.locator('.ant-table-tbody tr', { hasText: roleLabel });
  const input = roleRow.locator('input');
  const current = Number(await input.inputValue()) || 0;
  await d.click(input, `Проставьте остаток в «План Q» для роли «${roleLabel}»`);
  await input.press('Control+A');
  await input.pressSequentially(String(current + 8), { delay: 90 });
  await d.pause(500);
  await d.click(popover.getByRole('button', { name: 'Сохранить' }));
  await expect(popover).toBeHidden();
  await page.mouse.move(700, 120);

  const overrideTag = row.locator('.ant-tag', { hasText: 'переоценка' });
  await expect(overrideTag).toBeVisible({ timeout: 10_000 });
  await d.caption('Метка сменилась на «переоценка», нагрузка справа пересчиталась');
  await d.show(overrideTag);
  await d.pause(2200);

  await d.click(page.locator('[data-tour="planning-approve"]'), 'Нажмите «Утвердить» снова');
  await expect(page.locator('.ant-badge-status-text', { hasText: 'Утверждён' })).toBeVisible({ timeout: 15_000 });
  await d.pause(1000);

  await d.click(page.getByRole('button', { name: 'История' }), 'Откройте «История»');
  const historyDrawer = page.locator('.ant-drawer-open', { hasText: 'История ревизий сценария' });
  await expect(historyDrawer).toBeVisible({ timeout: 10_000 });
  await d.caption('Две последние ревизии: состав задач и доступность команды по месяцам');
  await d.show(historyDrawer.locator('.ant-tag').first());
  await d.pause(1400);
  await d.show(historyDrawer.getByText('Доступность команды'));
  await d.pause(2200);
  await d.click(historyDrawer.locator('.ant-drawer-close'), 'Закройте историю');
  await expect(historyDrawer).toBeHidden();

  if (compareScenarioName) {
    await d.click(page.getByRole('button', { name: 'Сравнить' }), 'Нажмите «Сравнить», чтобы сверить с другим сценарием');
    const compareDrawer = page.locator('.ant-drawer-open', { hasText: 'Сравнение сценариев' });
    await expect(compareDrawer).toBeVisible({ timeout: 10_000 });
    const bSelect = compareDrawer.locator('.ant-select').nth(1);
    await d.click(bSelect, 'Выберите второй сценарий');
    await d.click(
      page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: compareScenarioName }),
    );
    await expect(compareDrawer.locator('.ant-tag', { hasText: 'B' })).toBeVisible({ timeout: 10_000 });
    await d.caption('Зелёным — что есть только в одном сценарии, красным — только в другом');
    await d.show(compareDrawer.locator('.ant-tag', { hasText: 'A' }).first());
    await d.pause(1800);
    await d.click(compareDrawer.locator('.ant-drawer-close'), 'Закройте сравнение');
    await expect(compareDrawer).toBeHidden();
  }

  const downloadPromise = page.waitForEvent('download');
  await d.click(page.getByRole('button', { name: 'Экспорт' }), 'Нажмите «Экспорт» — сводка выгрузится в Excel');
  await downloadPromise;
  await d.pause(600);

  await d.caption('Готово', 2200);
  await d.save('scenario-review');
});
