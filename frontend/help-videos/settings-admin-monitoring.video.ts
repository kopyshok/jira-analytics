// Ролик «Как следить за сервисом: использование, обращения, ошибки»: Настройки (демо-администратор) →
// «Использование» (плитки, период, вкладки) → «Обратная связь» (сообщение, отметка прочитанным) →
// «Ошибки сервиса» (запись и копирование) → «Что нового» (черновики, просмотр как пользователь).
// В демо-базе этих данных нет: в beforeAll подсаживаем использование, обращения и черновики заметок
// в копию базы съёмки, список ошибок подменяем в браузере; в afterAll всё убираем.
// «Выпустить под версию…» и «Откатить версию» не нажимаем.
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

const fmt = (t: number) => new Date(t).toISOString().replace('T', ' ').replace('Z', '000');
const day = (t: number) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function clean(db: DatabaseSync) {
  for (const t of ['usage_daily', 'feedback_items', 'release_notes']) {
    db.exec(`DELETE FROM ${t} WHERE id LIKE '${SEED}%'`);
  }
}

function seed() {
  const db = new DatabaseSync(runDbPath());
  try {
    clean(db);
    const now = Date.now();
    const users = db.prepare(
      "SELECT id, email FROM users WHERE email IN ('demo@example.com', 'admin@example.com', 'user69@example.com', 'user153@example.com', 'user114@example.com', 'user177@example.com')",
    ).all() as { id: string; email: string }[];
    const paths = ['/', '/analytics', '/capacity', '/planning', '/team-desk', '/kpi', '/backlog', '/sync', '/resource-planning'];
    const insU = db.prepare(
      'INSERT INTO usage_daily (id, date, user_id, path, views, seconds, actions_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
    );
    db.exec('BEGIN');
    let n = 0;
    for (let back = 0; back < 45; back++) {
      const t = now - back * 86_400_000;
      const wd = new Date(t).getDay();
      if (wd === 0 || wd === 6) continue;
      users.forEach((u, ui) => {
        if ((back + ui) % 5 === 4) return; // у каждого свои выходные дни в сервисе
        paths.forEach((p, pi) => {
          if ((pi + ui + back) % 3 === 0) return;
          const views = 2 + ((pi * 3 + ui * 5 + back) % 9);
          insU.run(`${SEED}u${n++}`, day(t), u.id, p, views, views * (70 + ((pi + ui) % 5) * 55),
            '{}', fmt(t), fmt(t));
        });
      });
    }
    const author = (email: string) => users.find((u) => u.email === email)!.id;
    const insF = db.prepare(
      `INSERT INTO feedback_items (id, kind, author_id, title, body, page_url, read_at, read_by, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    );
    const rows: [string, string, string, string, string, number, boolean][] = [
      ['bug', 'user69@example.com', 'Не сохраняется оценка в сценарии', 'Меняю часы разработки у задачи, нажимаю Enter, после обновления страницы стоит старое значение.', '/planning', 3, false],
      ['bug', 'user153@example.com', 'Пустая таблица в «Ресурсах» после смены команды', 'Выбираю другую команду в шапке, таблица остаётся пустой, пока не обновишь страницу.', '/capacity', 26, false],
      ['bug', 'user114@example.com', 'Долго открывается Аналитика', 'За квартал отчёт собирается больше десяти секунд.', '/analytics', 70, true],
      ['idea', 'user177@example.com', 'Выгрузка сценария сразу в презентацию', 'Хотелось бы получать сводку сценария в виде слайдов для встречи с руководством.', '/planning', 5, false],
      ['idea', 'user69@example.com', 'Напоминание о незавершённом разборе задач', 'Раз в неделю присылать список задач без категории.', '/categories', 52, true],
    ];
    rows.forEach(([kind, email, title, body, url, hoursAgo, read], i) => {
      const at = now - hoursAgo * 3_600_000;
      insF.run(`${SEED}f${i}`, kind, author(email), title, body, url, read ? fmt(at + 3_600_000) : null,
        read ? author('admin@example.com') : null, fmt(at), fmt(at));
    });
    const insN = db.prepare(
      `INSERT INTO release_notes (id, version, note_type, section, title, description, help_link, is_hidden, sort_order, created_at, updated_at)
       VALUES (?, NULL, ?, ?, ?, ?, NULL, 0, ?, ?, ?)`,
    );
    const notes: [string, string, string, string][] = [
      ['new', 'analytics', 'Отчёт по видам работ', 'В «Аналитике» появился отчёт по видам работ с выгрузкой в Excel.'],
      ['improvement', 'scenarios', 'Быстрее открываются сценарии', 'Сценарий с сотнями задач теперь открывается почти мгновенно.'],
      ['fix', 'resources', 'Исправлена сумма отпусков', 'Отпуск на стыке кварталов больше не считается дважды.'],
    ];
    notes.forEach(([type, section, title, desc], i) => {
      insN.run(`${SEED}n${i}`, type, section, title, desc, 900 + i, fmt(now), fmt(now));
    });
    db.exec('COMMIT');
  } finally {
    db.close();
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

const FAKE_TRACE = (kind: string, msg: string) =>
  `Traceback (most recent call last):\n  File "app/api/endpoints/analytics.py", line 120, in get_report\n    rows = service.build(team)\n  File "app/services/analytics_service.py", line 88, in build\n    return self.db.execute(query).all()\n${kind}: ${msg}`;

const FAKE_ERRORS = () => {
  const now = Date.now();
  const item = (id: string, minAgo: number, method: string, path: string, type: string, message: string, user: string) => ({
    id, at: new Date(now - minAgo * 60_000).toISOString(), method, path, query: '', error_type: type, message,
    traceback: FAKE_TRACE(type, message), user,
  });
  return {
    started_at: new Date(now - 9 * 3_600_000).toISOString(),
    capacity: 200,
    items: [
      item('E-4F21A9', 14, 'GET', '/api/v1/analytics/report', 'TimeoutError', 'Запрос к базе не завершился за 30 секунд', 'Демо Пользователь'),
      item('E-3C07B2', 95, 'POST', '/api/v1/planning/scenarios/{scenario_id}/approve', 'IntegrityError', 'Нарушено ограничение уникальности при записи ревизии', 'Демо Пользователь'),
      item('E-19D8E0', 240, 'GET', '/api/v1/capacity/team', 'OperationalError', 'Не удалось подключиться к базе данных', 'Демо Администратор'),
    ],
  };
};

test('settings-admin-monitoring', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await page.route('**/api/v1/admin/errors', (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(FAKE_ERRORS()) });
  });

  const menu = (text: string) => page.locator('.ant-menu-item', { hasText: text });
  const toTop = () => page.evaluate(() => {
    window.scrollTo({ top: 0 });
    for (let el = document.querySelector('.ant-menu'); el; el = el.parentElement) if (el.scrollTop) el.scrollTop = 0;
  });

  await d.open('/settings#usage', 'Как следить за сервисом');
  await expect(page.locator('[data-tour="usage-kpi"] .ant-statistic').first()).toBeVisible();
  await expect(page.locator('[data-tour="usage-tabs"] .ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await toTop();
  await d.caption('«Использование» показывает, кто и сколько работает в сервисе');
  await d.show(page.locator('[data-tour="usage-kpi"]'));
  await d.click(page.locator('[data-tour="usage-period"]').getByText('7 дней'), 'Период выбирают кнопками');
  await d.click(page.locator('[data-tour="usage-tabs"]').getByRole('tab', { name: 'Разделы' }), 'Вкладка «Разделы» — какие экраны нужны людям');
  await d.waitVoice();

  await d.click(menu('Обратная связь'), 'Обращения пользователей — в «Обратной связи»');
  await toTop();
  await expect(page.locator('.ant-table-row', { hasText: 'Не сохраняется оценка' })).toBeVisible();
  await d.caption('Баги и идеи лежат отдельно, новые помечены');
  await d.show(page.locator('.ant-table-row', { hasText: 'Не сохраняется оценка' }));
  await d.click(page.locator('.ant-table-row', { hasText: 'Не сохраняется оценка' }).locator('td').nth(2), 'Откройте сообщение, чтобы прочитать подробности');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await d.pause(1500);
  await d.waitVoice();
  await d.click(drawer.locator('.ant-drawer-close'));
  await expect(drawer).toBeHidden();
  await d.click(page.locator('.ant-table-row', { hasText: 'Не сохраняется оценка' }).locator('input[type="checkbox"]'), 'Отметьте разобранное и нажмите «Отметить прочитанными»');
  await d.click(page.locator('button.ant-btn', { hasText: /^Отметить прочитанными$/ }));
  await expect(page.locator('.ant-notification').getByText('Отмечено прочитанными')).toBeVisible();
  await page.mouse.move(60, 120);

  await d.click(menu('Ошибки сервиса'), 'Сбои сервиса собраны в «Ошибках сервиса»');
  await toTop();
  const errRow = page.locator('.ant-table-row', { hasText: 'не ответила вовремя' });
  await expect(errRow).toBeVisible();
  await d.caption('Видно, когда, где и у кого случился сбой');
  await d.show(errRow);
  await d.click(errRow.locator('.ant-table-row-expand-icon'), 'Раскройте запись — её можно скопировать и приложить к обращению');
  await expect(page.locator('.ant-table-expanded-row')).toBeVisible();
  await d.show(page.locator('.ant-table-expanded-row'));
  await d.waitVoice();
  await toTop();
  await d.show(page.locator('[data-tour="errors-toolbar"]'));
  await d.caption('Время запуска сервиса видно рядом с кнопкой «Обновить»');
  await d.waitVoice();

  await d.click(menu('Что нового'), 'Заметки к релизу готовят в «Что нового»');
  await toTop();
  await expect(page.locator('[data-tour="notes-drafts"]')).toBeVisible();
  await d.caption('Черновики ждут выпуска, а ниже — история версий');
  await d.show(page.locator('[data-tour="notes-drafts"]'), page.locator('.ant-table-row', { hasText: 'Исправлена сумма отпусков' }));
  await d.click(page.getByRole('button', { name: /Посмотреть как пользователь/ }), 'Посмотрите, как заметки увидят пользователи');
  const modal = page.locator('.ant-modal', { hasText: 'Отчёт по видам работ' });
  await expect(modal).toBeVisible();
  await d.pause(1800);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await expect(modal).toBeHidden();
  await toTop();
  await d.caption('Когда черновики готовы, версию выпускают отдельной кнопкой');
  await d.show(page.locator('[data-tour="notes-drafts"]'), page.locator('.ant-table-row', { hasText: 'Исправлена сумма отпусков' }));

  await d.caption('Готово', 2200);
  await d.save('settings-admin-monitoring');
});
