// Ролик «Как настроить оценку KPI для роли»: Настройки → «KPI» (демо-администратор):
// новый профиль оценки для роли (роли, две метрики, веса до «сходится») → «Покрытие ролей
// профилями» → «Конструктор метрики» и «Предпросмотр на реальных данных» → «Нормативы»
// → «Общие правила» (утверждение квартала). Метрики и правила не сохраняются; созданный
// профиль удаляется в afterAll.
import { expect, test } from '@playwright/test';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const PROFILE = 'Профиль тестирования';
const ROLE = 'Тестировщик';
const TEAM = 'Команда Альфа';

async function removeProfile(playwright: import('@playwright/test').PlaywrightWorkerArgs['playwright'], backend: string) {
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  const res = await request.get(`${backend}/api/v1/kpi-settings/profiles`);
  expect(res.ok()).toBeTruthy();
  for (const p of (await res.json()) as { id: string; name: string; [k: string]: unknown }[]) {
    if (p.name !== PROFILE) continue;
    // Профиль с ролями удалить нельзя — сначала снимаем роли.
    const { id, ...body } = p;
    const upd = await request.put(`${backend}/api/v1/kpi-settings/profiles/${id}`, {
      data: {
        code: body.code, name: body.name, role_codes: [], target_pct: body.target_pct,
        warn_band_pct: body.warn_band_pct, is_enabled: body.is_enabled,
        metrics: (body.metrics as { metric_code: string; weight: number; sort_order: number }[])
          .map((m) => ({ metric_code: m.metric_code, weight: m.weight, sort_order: m.sort_order })),
      },
    });
    expect(upd.ok(), `${upd.status()} ${await upd.text()}`).toBeTruthy();
    const del = await request.delete(`${backend}/api/v1/kpi-settings/profiles/${id}`);
    expect(del.ok(), `${del.status()} ${await del.text()}`).toBeTruthy();
  }
  await request.dispose();
}

test.beforeAll(async ({ playwright }, testInfo) => {
  await removeProfile(playwright, String(testInfo.config.metadata.backendUrl));
});

test.afterAll(async ({ playwright }, testInfo) => {
  await removeProfile(playwright, String(testInfo.config.metadata.backendUrl));
});

test('settings-kpi', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const option = (text: string) => page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: text });
  const toTop = () => page.evaluate(() => {
    window.scrollTo({ top: 0 });
    for (let el = document.querySelector('.ant-tabs'); el; el = el.parentElement) if (el.scrollTop) el.scrollTop = 0;
  });
  const typeNumber = async (input: import('@playwright/test').Locator, value: string) => {
    await d.click(input);
    await page.keyboard.press('Control+A');
    await page.keyboard.type(value, { delay: 40 });
    await page.keyboard.press('Tab');
    await d.pause(300);
  };

  await d.open('/settings#kpi', 'Как настроить оценку KPI для роли');
  await expect(page.getByRole('button', { name: /Создать профиль/ })).toBeVisible();
  await expect(page.locator('[data-tour="kpi-coverage"] .ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await toTop();
  await d.caption('Ведомость KPI строится по профилям оценки');
  await d.show(page.getByRole('button', { name: /Создать профиль/ }));
  await d.click(page.getByRole('button', { name: /Создать профиль/ }), 'Создайте профиль для роли, которую ещё не оценивают');

  const main = page.locator('[data-tour="kpi-profile-main"]');
  await expect(main).toBeVisible();
  await main.locator('input').nth(0).fill('tester');
  await d.type(main.locator('input').nth(1), PROFILE, 'Назовите профиль и выберите роли, которых он оценивает');
  await d.click(main.locator('.ant-select'));
  await d.click(option(ROLE));
  await page.keyboard.press('Escape');
  await page.mouse.move(60, 120);

  const metrics = page.locator('[data-tour="kpi-profile-metrics"]');
  await d.click(metrics.locator('.ant-select'), 'Добавьте метрики и разведите веса');
  await d.click(option('Качество выпуска'));
  await d.click(metrics.locator('.ant-select'));
  await d.click(option('Соблюдение сроков'));
  const inputs = metrics.locator('.ant-input-number input');
  await typeNumber(inputs.nth(0), '60');
  await typeNumber(inputs.nth(1), '40');
  await expect(metrics.getByText(/сходится/)).toBeVisible();
  await d.caption('Сумма весов должна быть ровно сто процентов');
  await d.show(metrics.getByText(/сходится/));
  await d.waitVoice();

  await d.click(page.locator('[data-tour="kpi-profile-save"]'));
  await expect(page.locator('.ant-notification').getByText('Профиль создан')).toBeVisible();
  await page.mouse.move(60, 120);

  const coverage = page.locator('[data-tour="kpi-coverage"]');
  await expect(coverage.locator('.ant-table-row', { hasText: ROLE }).getByText('оценивается')).toBeVisible();
  await coverage.locator('.ant-table-row', { hasText: ROLE }).evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await d.caption('В покрытии роль «Тестировщик» теперь оценивается');
  await d.show(coverage.locator('.ant-table-row', { hasText: ROLE }));
  await d.caption('Роль сотрудника определяет профиль, по которому его оценят в разделе «KPI»');
  await d.waitVoice();

  await toTop();
  await d.click(page.getByRole('tab', { name: 'Конструктор метрики' }), 'Метрику собирают в конструкторе — выберите её из списка');
  await d.click(page.locator('.ant-select').filter({ hasText: 'Выберите метрику' }).first());
  await d.click(option('Соблюдение сроков'));
  const sets = page.locator('[data-tour="kpi-condition-set"]');
  await expect(sets.first()).toBeVisible();
  await sets.first().evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await d.caption('Здесь задают, что считаем, чьи задачи и за какой период');
  await d.show(sets.first());
  await d.waitVoice();

  const preview = page.locator('[data-tour="kpi-preview"]');
  await preview.evaluate((e) => e.scrollIntoView({ block: 'start' }));
  await d.click(preview.locator('.ant-select').first(), 'Проверьте метрику на реальных данных: выберите команду и месяц');
  // Список команд длинный и рисуется частями — прокручиваем до нужной.
  for (let i = 0; i < 60 && !(await option(TEAM).count()); i++) {
    await page.locator('.ant-select-dropdown:visible .rc-virtual-list-holder').evaluate((e) => { e.scrollTop += 160; });
    await d.pause(80);
  }
  await d.click(option(TEAM));
  await d.click(preview.locator('.ant-picker input'));
  await d.click(page.locator('.ant-picker-dropdown:visible td[title="2026-10"]'));
  await d.click(preview.getByRole('button', { name: 'Посчитать' }));
  await expect(preview.getByText('Результат по команде')).toBeVisible();
  await preview.getByText('Результат по команде').evaluate((e) => e.scrollIntoView({ block: 'start' }));
  await d.caption('Видно результат, воронку отбора и значения по сотрудникам');
  await d.show(preview.getByText('Результат по команде'), preview.locator('.ant-table-tbody').first());
  await d.pause(1500);
  await d.waitVoice();

  await toTop();
  await d.click(page.getByRole('tab', { name: 'Нормативы Cycle Time' }));
  const norms = page.locator('.ant-tabs-tabpane-active');
  await expect(norms.locator('.ant-table-row').first()).toBeVisible();
  await d.caption('Нормативы времени цикла — по командам и кварталам, есть копирование прошлого');
  await d.show(norms.locator('.ant-card-head'));
  await d.waitVoice();

  await toTop();
  await d.click(page.getByRole('tab', { name: 'Общие правила' }));
  const approval = page.locator('[data-tour="kpi-approval"]');
  await expect(approval).toBeVisible();
  await approval.evaluate((e) => e.scrollIntoView({ block: 'center' }));
  await d.caption('В общих правилах включают утверждение квартала');
  await d.show(approval);
  await d.pause(800);

  await d.caption('Готово', 2200);
  await d.save('settings-kpi');
});
