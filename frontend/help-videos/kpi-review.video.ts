// Ролик «Как разобрать KPI сотрудника и утвердить квартал»: период месяц →
// квартал → ведомость команды → вкладка сотрудника → расчёт метрики → назад
// → утверждение квартала (если включено администратору) → выгрузка в Excel.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const QUARTER_LABELS = [
  'I квартал (янв–мар)', 'II квартал (апр–июн)', 'III квартал (июл–сен)', 'IV квартал (окт–дек)',
];

interface KpiMetricValue {
  code: string;
  name: string;
  value: number | null;
  has_data: boolean;
}
interface KpiReportRow {
  employee_id: string;
  employee_name: string;
  account_id: string;
  team: string | null;
  total: number | null;
  metrics: KpiMetricValue[];
}
interface KpiReport {
  approval_enabled: boolean;
  rows: KpiReportRow[];
}
interface KpiBreakdown {
  table: { problem_count: number; kind: string; dropped: unknown[] };
}

function dbPathFromBackendUrl(backendUrl: string): string {
  const port = new URL(backendUrl).port;
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

/** Утверждение квартала снять может только прямая правка базы: в API раздела
 * нет отмены — «утверждён» окончательно с точки зрения интерфейса. */
function clearApproval(dbPath: string, team: string, year: number, quarter: number) {
  try {
    const db = new DatabaseSync(dbPath);
    try {
      db.prepare('DELETE FROM kpi_approvals WHERE team = ? AND year = ? AND quarter = ?').run(team, year, quarter);
    } finally {
      db.close();
    }
  } catch {
    // Лучшее из возможного: файл занят сервером — не роняем ролик из-за уборки.
  }
}

let year = 0;
let quarterNum = 0;
let anchorMonth = 0;
let approvalEnabled = false;
let employeeName = '';
let metricName = '';
let hasDropped = false;
let approvedThisRun = false;
let dbPath = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const backendUrl = String(testInfo.config.metadata.backendUrl);
  const api = `${backendUrl}/api/v1`;
  dbPath = dbPathFromBackendUrl(backendUrl);
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Утверждение обычно выключено, пока раздел обкатывают, и включить его
  // может только администратор — демо-пользователь им не является. Пробуем
  // на случай, если это когда-нибудь изменится, но не полагаемся на успех.
  await request.put(`${api}/kpi-settings/general`, {
    data: {
      excluded_statuses: ['Отменено'], worklog_deadline_mode: 'hours_from_start',
      worklog_deadline_hours: 18, worklog_deadline_days: 1, worklog_deadline_time: '12:00',
      empty_policy: 'redistribute', approval_enabled: true,
    },
  }).catch(() => undefined);

  // Ищем квартал, где у команды реально есть данные — в демо они есть не
  // везде; берём тот, где метрик с числом больше всего.
  const now = new Date();
  let q = Math.floor(now.getMonth() / 3) + 1;
  let y = now.getFullYear();
  let best: { year: number; quarter: number; score: number; report: KpiReport } | null = null;
  for (let i = 0; i < 8; i++) {
    const res = await request.get(`${api}/kpi/report`, {
      params: { year: String(y), month: String(q * 3), months: '3', teams: TEAM },
    });
    if (res.ok()) {
      const report = (await res.json()) as KpiReport;
      const score = report.rows.reduce(
        (sum, row) => sum + row.metrics.filter((m) => m.has_data && m.value != null).length, 0,
      );
      if (!best || score > best.score) best = { year: y, quarter: q, score, report };
    }
    q -= 1;
    if (q === 0) { q = 4; y -= 1; }
  }
  expect(best && best.score > 0, `нет данных KPI по команде «${TEAM}» ни в одном из последних кварталов`).toBeTruthy();
  year = best!.year;
  quarterNum = best!.quarter;
  anchorMonth = (quarterNum - 1) * 3 + 1;
  approvalEnabled = best!.report.approval_enabled;

  // Сотрудник с самым низким итогом — на нём удобнее всего показывать разбор
  // причины; среди его метрик предпочитаем ту, где реально есть нарушения.
  const evaluated = best!.report.rows.filter((r) => r.total != null);
  expect(evaluated.length, 'нет оценённых сотрудников в этом периоде').toBeGreaterThan(0);
  const employee = [...evaluated].sort((a, b) => (a.total ?? 0) - (b.total ?? 0))[0];
  employeeName = employee.employee_name;

  const withData = employee.metrics.filter((m) => m.has_data && m.value != null);
  let chosenMetric = withData[0];
  let bestScore = -1;
  for (const m of withData) {
    const br = await request.get(`${api}/kpi/breakdown`, {
      params: {
        account_id: employee.account_id, metric_code: m.code,
        year: String(year), month: String(anchorMonth + 2), months: '3',
      },
    });
    if (br.ok()) {
      const data = (await br.json()) as KpiBreakdown;
      // Лучше всего — метрика и с ошибками, и со списком «Отсеяно до сравнения».
      const score = (data.table.problem_count > 0 ? 1 : 0)
        + (data.table.dropped.length > 0 && data.table.kind !== 'worklogs' ? 2 : 0);
      if (score > bestScore) {
        bestScore = score; chosenMetric = m; hasDropped = score >= 2;
      }
      if (score === 3) break;
    }
  }
  metricName = chosenMetric.name;

  // Утверждение — по одной команде и ровно на квартал; чистим возможный след
  // прошлого прогона на этой же копии базы, чтобы кнопка была активна.
  clearApproval(dbPath, TEAM, year, quarterNum);
  await request.dispose();
});

test.afterAll(async () => {
  if (approvedThisRun) clearApproval(dbPath, TEAM, year, quarterNum);
});

test('kpi-review', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(
    `/kpi?kpiYear=${year}&kpiMonth=${anchorMonth}&kpiMonths=1`,
    'Как разобрать KPI сотрудника и утвердить квартал',
  );

  const ledgerCard = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Ведомость' }) });
  await expect(ledgerCard).toBeVisible({ timeout: 20_000 });
  await d.pause(1300);
  await d.poster();
  await d.pause(1500);

  await d.caption('Месяц — обычный вид для контроля внутри периода');
  await d.show(page.locator('.ant-segmented').first());
  await d.pause(1900);

  await d.click(
    page.locator('.ant-segmented-item', { hasText: 'Квартал' }),
    'Переключите на «Квартал», чтобы закрыть период целиком',
  );
  await expect(ledgerCard.getByRole('button', { name: employeeName, exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(QUARTER_LABELS[quarterNum - 1]).first()).toBeVisible();
  await d.pause(1400);

  await d.caption('Ведомость команды — метрики и итог по каждому');
  await d.show(ledgerCard);
  await d.pause(2200);

  const nameButton = ledgerCard.getByRole('button', { name: employeeName, exact: true });
  await d.click(nameButton, 'Клик по имени открывает вкладку сотрудника');

  // Шапка сотрудника — единственная карточка с кольцом прогресса.
  const empHeader = page.locator('.ant-card', { has: page.locator('.ant-progress-circle') });
  await expect(empHeader).toBeVisible();
  await d.pause(500);
  await d.caption('Кольцо — итог, рядом место в команде');
  await d.show(empHeader);
  await d.pause(2000);

  const contribCard = page.locator('.ant-card', {
    has: page.locator('.ant-card-head', { hasText: 'Из чего сложился итог' }),
  });
  await d.caption('«Из чего сложился итог» — вклад каждой метрики в процентных пунктах');
  await d.show(contribCard);
  await d.pause(600);

  const trendCard = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Тренд за 12 месяцев' }) });
  await d.caption('«Тренд за 12 месяцев» — как менялся итог сотрудника');
  await trendCard.scrollIntoViewIfNeeded();
  await d.show(trendCard);
  await d.pause(800);

  await d.waitVoice();
  const metricsCard = page.locator('.ant-card', {
    has: page.locator('.ant-card-head', { hasText: 'Разбор по метрикам' }),
  });
  const metricCard = metricsCard.locator('[role="button"]', { hasText: metricName });
  await d.click(metricCard, `Нажмите на карточку метрики «${metricName}»`);

  const dock = page.locator('section[aria-label^="Расчёт показателя"]');
  await expect(dock).toBeVisible({ timeout: 10_000 });
  await d.pause(600);
  await d.caption('Панель расчёта — дробь и разбор по задачам');
  await d.show(dock);
  await d.pause(2400);

  // Вторая опция сегмента — «Нарушения»/«С ошибкой» в зависимости от метрики,
  // но не «Все ·…»: находим по тому, что название не начинается с «Все».
  const problemToggle = dock.locator('.ant-segmented-item').filter({ hasNotText: /^Все/ });
  await d.click(problemToggle, 'Оставьте только проблемные строки');
  await expect(dock.locator('.ant-segmented-item-selected')).not.toContainText('Все');
  await d.pause(900);

  const firstRow = dock.locator('.ant-table-tbody tr').first();
  if (await firstRow.count()) {
    await d.caption('Номер задачи — ссылка в Jira');
    await d.show(firstRow.locator('td').first());
    await d.pause(2000);
  }

  const droppedHeader = dock.locator('.ant-collapse-header', { hasText: 'Отсеяно до сравнения' });
  if (hasDropped && (await droppedHeader.count())) {
    await d.click(droppedHeader, '«Отсеяно до сравнения» — задачи, которые в расчёт не вошли');
    await d.pause(900);
  }

  const funnelHeader = page.locator('.ant-collapse-header', { hasText: 'Как получилось это число' });
  await d.click(funnelHeader, 'Раскройте «Как получилось это число» — отбор по шагам');
  await d.pause(2400);

  await d.click(dock.getByRole('button', { name: 'Свернуть' }), 'Назад к ведомости');
  await expect(dock).toBeHidden();
  await d.pause(1000);

  if (approvalEnabled) {
    const approveTag = page.locator('.ant-tag', { hasText: 'Черновик, не утверждён' });
    await d.caption('Квартал ещё не утверждён');
    await d.show(approveTag);
    await d.pause(1300);

    await d.click(
      page.getByRole('button', { name: 'Утвердить квартал' }),
      'Утвердите квартал — результат заморозится снимком',
    );
    await expect(page.getByText(/Утвердил/).first()).toBeVisible({ timeout: 10_000 });
    approvedThisRun = true;
    await d.caption('Плашка «Квартал утверждён» — числа заморожены снимком');
    await d.show(page.locator('.ant-alert', { hasText: 'Квартал утверждён' }));
    await d.pause(1900);
  } else {
    await d.caption('Утверждение квартала пока выключено администратором в настройках');
    await d.show(page.getByRole('button', { name: 'Выгрузить в Excel' }));
    await d.pause(2200);
  }

  await d.click(page.getByRole('button', { name: 'Выгрузить в Excel' }), 'Выгрузите ведомость в Excel');
  await d.pause(1200);

  await d.show(ledgerCard);
  await d.caption('Готово', 2200);
  await d.pause(500);
  await d.save('kpi-review');
});
