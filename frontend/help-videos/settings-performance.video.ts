// Ролик «Как понять, почему сервис работает медленно»: Настройки → «Быстродействие»
// (от имени демо-администратора): период, плитки, причины медленных запросов, график с
// подсказкой, «Узкие места», раскрытая строка «Медленные запросы», отчёт и Excel (только нажатие).
// В демо-базе замеров нет — в beforeAll подсаживаем правдоподобные замеры за сутки в копию
// базы съёмки (perf_minute, perf_slow_request, perf_server_snapshot), в afterAll убираем.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const SEED = 'video-seed-';

function runDbPath(): string {
  const port = process.env.VIDEOS_BACKEND_PORT ?? '8012';
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

const HIST_BOUNDS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 30000];
const fmt = (t: number) => new Date(t).toISOString().replace('T', ' ').replace('Z', '000');

/** Детерминированный генератор: ролик снимается одинаково при каждом прогоне. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
}

const ROUTES: { method: string; route: string; perMin: number; ms: number; dbMs: number; dbCount: number }[] = [
  { method: 'GET', route: '/api/v1/analytics/report', perMin: 3, ms: 420, dbMs: 0.7, dbCount: 14 },
  { method: 'GET', route: '/api/v1/capacity/team', perMin: 4, ms: 260, dbMs: 0.6, dbCount: 22 },
  { method: 'GET', route: '/api/v1/planning/scenarios/{scenario_id}', perMin: 3, ms: 180, dbMs: 0.5, dbCount: 9 },
  { method: 'GET', route: '/api/v1/backlog', perMin: 2, ms: 340, dbMs: 0.65, dbCount: 17 },
  { method: 'GET', route: '/api/v1/team-desk/overview', perMin: 2, ms: 520, dbMs: 0.55, dbCount: 31 },
  { method: 'GET', route: '/api/v1/analytics/dashboard/hours-balance', perMin: 2, ms: 150, dbMs: 0.5, dbCount: 6 },
  { method: 'GET', route: '/api/v1/kpi/report', perMin: 1, ms: 610, dbMs: 0.6, dbCount: 28 },
  { method: 'PUT', route: '/api/v1/planning/scenarios/{scenario_id}/allocations/{allocation_id}', perMin: 1, ms: 90, dbMs: 0.6, dbCount: 5 },
];

type SlowSpec = {
  minAgo: number; route: number; user: 'demo' | 'admin'; dur: number; db: number; cpu: number; path: string;
  verdict: 'other_load' | 'database' | 'our_code' | 'db_pool' | 'waiting';
};
// Минуты «назад» подобраны так, чтобы на графике было три всплеска.
const SLOW: SlowSpec[] = [
  { minAgo: 205, route: 0, user: 'demo', dur: 4800, db: 900, cpu: 700, path: '/api/v1/analytics/report', verdict: 'other_load' },
  { minAgo: 198, route: 4, user: 'demo', dur: 6100, db: 1200, cpu: 800, path: '/api/v1/team-desk/overview', verdict: 'other_load' },
  { minAgo: 192, route: 1, user: 'admin', dur: 3900, db: 700, cpu: 500, path: '/api/v1/capacity/team', verdict: 'other_load' },
  { minAgo: 189, route: 0, user: 'demo', dur: 5300, db: 1000, cpu: 900, path: '/api/v1/analytics/report', verdict: 'other_load' },
  { minAgo: 183, route: 6, user: 'demo', dur: 4400, db: 800, cpu: 600, path: '/api/v1/kpi/report', verdict: 'other_load' },
  { minAgo: 540, route: 3, user: 'demo', dur: 5200, db: 1700, cpu: 600, path: '/api/v1/backlog', verdict: 'db_pool' },
  { minAgo: 536, route: 4, user: 'admin', dur: 6700, db: 2100, cpu: 700, path: '/api/v1/team-desk/overview', verdict: 'db_pool' },
  { minAgo: 531, route: 1, user: 'demo', dur: 4100, db: 1300, cpu: 500, path: '/api/v1/capacity/team', verdict: 'db_pool' },
  { minAgo: 95, route: 6, user: 'demo', dur: 4300, db: 3300, cpu: 600, path: '/api/v1/kpi/report', verdict: 'database' },
  { minAgo: 410, route: 0, user: 'demo', dur: 7200, db: 5600, cpu: 900, path: '/api/v1/analytics/report', verdict: 'database' },
  { minAgo: 620, route: 6, user: 'admin', dur: 3800, db: 2900, cpu: 500, path: '/api/v1/kpi/report', verdict: 'database' },
  { minAgo: 1010, route: 0, user: 'demo', dur: 3600, db: 600, cpu: 2800, path: '/api/v1/analytics/report', verdict: 'our_code' },
  { minAgo: 760, route: 4, user: 'demo', dur: 4900, db: 800, cpu: 4000, path: '/api/v1/team-desk/overview', verdict: 'our_code' },
  { minAgo: 300, route: 2, user: 'admin', dur: 2700, db: 300, cpu: 250, path: '/api/v1/planning/scenarios/abc', verdict: 'waiting' },
  { minAgo: 40, route: 3, user: 'demo', dur: 2500, db: 250, cpu: 200, path: '/api/v1/backlog', verdict: 'waiting' },
  { minAgo: 1230, route: 1, user: 'demo', dur: 2900, db: 350, cpu: 300, path: '/api/v1/capacity/team', verdict: 'waiting' },
];

const SQL_SAMPLES = [
  'SELECT issues.id, issues.key, issues.summary, issues.status FROM issues WHERE issues.project_id IN (?, ?, ?) ORDER BY issues.updated_at DESC',
  'SELECT worklogs.id, worklogs.issue_id, worklogs.time_spent_seconds FROM worklogs JOIN issues ON issues.id = worklogs.issue_id WHERE worklogs.started >= ?',
  'SELECT employees.id, employees.display_name, employee_team_memberships.team FROM employees LEFT JOIN employee_team_memberships ON employee_team_memberships.employee_id = employees.id',
];

function seed() {
  const db = new DatabaseSync(runDbPath());
  try {
    clean(db);
    const now = Date.now();
    const rnd = rng(20261004);
    const users = db.prepare("SELECT id, email FROM users WHERE email IN ('demo@example.com', 'admin@example.com')").all() as { id: string; email: string }[];
    const uid = (k: 'demo' | 'admin') => users.find((u) => u.email === `${k}@example.com`)?.id ?? null;

    const insMin = db.prepare(
      `INSERT INTO perf_minute (id, minute, method, route, count, total_ms, max_ms, errors_5xx, db_count, db_ms,
        h0, h1, h2, h3, h4, h5, h6, h7, h8, h9, h10, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    );
    const insSnap = db.prepare(
      `INSERT INTO perf_server_snapshot (id, at, host_cpu_percent, host_memory_percent, process_cpu_percent, process_memory_mb,
        cpu_count, threads, db_pool_in_use, db_pool_size, requests_in_flight, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    );
    const insSlow = db.prepare(
      `INSERT INTO perf_slow_request (id, at, method, route, path, "query", status_code, duration_ms, db_count, db_ms, cpu_ms,
        user_id, top_queries, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    );

    db.exec('BEGIN');
    const floorMin = (t: number) => Math.floor(t / 60_000) * 60_000;
    let n = 0;
    // Минутные агрегаты за сутки: через минуту, чтобы вставка шла быстро.
    for (let m = 24 * 60; m >= 1; m -= 2) {
      const t = floorMin(now - m * 60_000);
      const busy = (m >= 178 && m <= 210) || (m >= 525 && m <= 545);
      for (const r of ROUTES) {
        const count = Math.max(0, Math.round(r.perMin * 2 * (0.4 + rnd() * 1.2) * (m % 1440 > 1100 ? 0.3 : 1)));
        if (!count) continue;
        const hist = new Array(11).fill(0);
        let total = 0;
        let max = 0;
        for (let i = 0; i < count; i++) {
          const d = r.ms * (0.35 + rnd() * 1.3) * (busy ? 1.8 : 1) + (rnd() < 0.01 ? 2200 : 0);
          total += d;
          max = Math.max(max, d);
          hist[HIST_BOUNDS.findIndex((b) => d <= b) === -1 ? 10 : HIST_BOUNDS.findIndex((b) => d <= b)]++;
        }
        const e5 = busy && rnd() < 0.05 ? 1 : 0;
        insMin.run(`${SEED}m${n++}`, fmt(t), r.method, r.route, count, total, max, e5,
          Math.round(count * r.dbCount), total * r.dbMs, ...hist, fmt(t), fmt(t));
      }
    }
    // Снимки нагрузки раз в минуту.
    for (let m = 24 * 60; m >= 0; m--) {
      const t = floorMin(now - m * 60_000) + 50_000;
      if (t > now) continue;
      const spike = m >= 180 && m <= 208;
      const pool = m >= 527 && m <= 543;
      const host = spike ? 90 + rnd() * 7 : 22 + rnd() * 16 + (m > 400 && m < 700 ? 8 : 0);
      const proc = spike ? 30 + rnd() * 15 : 28 + rnd() * 30;
      insSnap.run(`${SEED}s${n++}`, fmt(t), host, 48 + rnd() * 6, proc, 520 + rnd() * 40, 4, 38 + Math.round(rnd() * 8),
        pool ? 5 : Math.round(rnd() * 2), 5, pool ? 14 + Math.round(rnd() * 4) : 1 + Math.round(rnd() * 4), fmt(t), fmt(t));
    }
    for (const s of SLOW) {
      const r = ROUTES[s.route];
      const t = floorMin(now - s.minAgo * 60_000) + 20_000;
      const tops = [
        { ms: Math.round(s.db * 0.55), sql: SQL_SAMPLES[(s.route + 0) % 3] },
        { ms: Math.round(s.db * 0.25), sql: SQL_SAMPLES[(s.route + 1) % 3] },
      ];
      insSlow.run(`${SEED}r${n++}`, fmt(t), r.method, r.route, s.path, '', 200, s.dur, Math.round(r.dbCount * 1.2),
        s.db, s.cpu, uid(s.user), JSON.stringify(tops), fmt(t), fmt(t));
    }
    db.exec('COMMIT');
  } finally {
    db.close();
  }
}

function clean(db: DatabaseSync) {
  for (const t of ['perf_minute', 'perf_slow_request', 'perf_server_snapshot']) {
    db.exec(`DELETE FROM ${t} WHERE id LIKE '${SEED}%'`);
  }
}

test.beforeAll(() => {
  seed();
});

test.afterAll(() => {
  const db = new DatabaseSync(runDbPath());
  try {
    clean(db);
  } finally {
    db.close();
  }
});

test('settings-performance', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/settings#perf', 'Как понять, почему сервис работает медленно');
  await expect(page.locator('[data-tour="perf-slow"] .ant-table-row').first()).toBeVisible();
  await expect(page.locator('[data-tour="perf-chart"] .recharts-wrapper')).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await page.evaluate(() => window.scrollTo({ top: 0 }));
  await d.caption('В настройках откройте «Быстродействие»: сервис замеряет каждое обращение и хранит замеры тридцать дней');
  await d.show(page.locator('[data-tour="perf-about"]'));

  const toolbar = page.locator('[data-tour="perf-toolbar"]');
  await d.click(toolbar.getByText('7 дней'), 'Период выбирают кнопками');
  await expect(page.locator('[data-tour="perf-chart"] .recharts-wrapper')).toBeVisible();
  await d.click(toolbar.getByText('Сутки'));
  await expect(page.locator('[data-tour="perf-slow"] .ant-table-row').first()).toBeVisible();

  await d.caption('Сверху — сколько было запросов, медленных и сбоев');
  await d.show(page.locator('[data-tour="perf-tiles"]'));

  await d.caption('Метки объясняют, почему запросы были медленными');
  await d.show(page.locator('[data-tour="perf-verdicts"]'));

  // Подсказка точки графика с выводом о причине: ищем всплеск мышью.
  const chart = page.locator('[data-tour="perf-chart"] .recharts-wrapper');
  await d.caption('На графике подсказка точки говорит о причине');
  await page.locator('[data-tour="perf-chart"]').evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await d.show(page.locator('[data-tour="perf-chart"]'));
  const box = (await chart.boundingBox())!;
  const tip = page.locator('.recharts-tooltip-wrapper');
  let found = false;
  for (let x = box.x + box.width - 50; x > box.x + 70 && !found; x -= 14) {
    await page.mouse.move(x, box.y + 160);
    await d.pause(60);
    const text = (await tip.innerText().catch(() => '')) || '';
    if (/сервер загружен|Чаще всего/.test(text)) found = true;
  }
  expect(found, 'на графике нет точки с причиной').toBeTruthy();
  await d.pause(1800);
  await d.waitVoice();
  await page.mouse.move(60, 120);

  await d.caption('«Узкие места» показывают, какие запросы заставляют ждать сильнее всего');
  await d.show(page.locator('[data-tour="perf-bottlenecks"]'));
  await d.click(page.locator('[data-tour="perf-bottlenecks"] th', { hasText: 'В среднем' }).first(), 'Колонки таблицы можно сортировать');

  const slow = page.locator('[data-tour="perf-slow"]');
  await d.click(slow.locator('.ant-table-row-expand-icon').first(), 'Раскройте медленный запрос');
  await expect(slow.locator('.ant-table-expanded-row')).toBeVisible();
  await d.caption('Внутри — вывод о причине и самые долгие обращения к базе');
  await slow.locator('.ant-table-expanded-row').evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await d.show(slow.locator('.ant-table-expanded-row'));
  await d.waitVoice();

  await page.evaluate(() => window.scrollTo({ top: 0 }));
  await page.locator('[data-tour="perf-toolbar"]').scrollIntoViewIfNeeded();
  await d.click(toolbar.getByRole('button', { name: /Отчёт для разработки/ }), 'Отчёт для разработки собирает всё нужное в один файл');
  await d.pause(800);
  await d.click(toolbar.getByRole('button', { name: /Excel/ }), 'Эти же данные можно выгрузить в Excel');
  await d.pause(800);
  await page.mouse.move(60, 120);
  await d.caption('Передайте файл разработчикам вместе с обращением — они увидят причину');
  await d.show(toolbar);
  await d.pause(600);

  await d.caption('Сбои сервера собраны отдельно, в «Ошибках сервиса»');
  await d.pause(300);
  await d.caption('Готово', 2200);
  await d.save('settings-performance');
});
