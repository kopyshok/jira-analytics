// Ролик «Как построить ресурсный план»: Ресурсное планирование → утверждённый
// сценарий квартала → «Распределить» → фазы на диаграмме и загрузка по дням.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

type Scenario = { id: string; name: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };

test('resource-plan-build', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Подготовка до первого кадра. План последнего утверждённого сценария команды
  // удаляется: в ролике он строится с нуля — пустой план, «Распределить», результат.
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const prefs = await page.request.patch(`${api}/resource-planning/preferences`, {
    data: { view_mode: 'tasks', hide_weekends: false, collapsed_initiative_ids: [] },
  });
  expect(prefs.ok()).toBeTruthy();
  const scenarios: Scenario[] = await (
    await page.request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } })
  ).json();
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  if (!scenario) throw new Error(`Нет утверждённых сценариев команды ${TEAM}`);
  // Копии плана без родителя тоже попадают в список — удаляем, пока план сценария есть.
  for (let i = 0; i < 20; i++) {
    const plans: Plan[] = await (
      await page.request.get(`${api}/resource-planning/resource-plans`, { params: { team: TEAM } })
    ).json();
    const plan = plans.find((p) => p.scenario_id === scenario.id);
    if (!plan) break;
    expect((await page.request.delete(`${api}/resource-planning/resource-plans/${plan.id}`)).ok()).toBeTruthy();
  }

  await d.open('/resource-planning', 'Как построить ресурсный план');
  const select = page.locator('[data-tour="rp-scenario-select"]');
  await expect(select).toBeVisible();
  await expect(page.getByText('Выберите план или создайте его из утверждённого сценария')).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Ресурс. планир.' }), 'Откройте раздел «Ресурсное планирование»');
  await d.click(select, 'Выберите утверждённый сценарий квартала');
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', {
      hasText: `${scenario.quarter} ${scenario.year} — ${scenario.name}`,
    }),
  );

  const status = (text: string) => page.locator('.ant-tag', { hasText: new RegExp(`^${text}$`) });
  const gantt = page.locator('[data-tour="rp-gantt"]');
  await expect(status('Черновик')).toBeVisible();
  await expect(gantt).toBeVisible();
  await expect(page.locator('[data-testid^="rp-bar-"]')).toHaveCount(0);
  await page.mouse.move(900, 120);
  await d.caption('План создан, но фазы ещё не разложены');
  await d.show(status('Черновик'));
  await d.pause(1200);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await d.caption('Сервис разложил фазы по исполнителям и дням');
  await expect(status('Готово')).toBeVisible({ timeout: 60_000 });
  const bars = page.locator('[data-testid^="rp-bar-"]');
  await expect(bars.first()).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(1600);

  // Первая задача на диаграмме: полосы её фаз от первой до последней.
  const firstId = (await bars.first().getAttribute('data-testid')) ?? '';
  const item = /^rp-bar-(.+)-(analyst|dev|qa|opo)-\d+$/.exec(firstId)?.[1];
  if (!item) throw new Error(`Неожиданная метка полосы: ${firstId}`);
  const itemBars = page.locator(`[data-testid^="rp-bar-${item}-"]`);
  await d.caption('Каждая полоса — фаза задачи в календаре квартала');
  await d.show(itemBars.first(), itemBars.last());
  await d.pause(1800);

  // Блок загрузки — последний на странице: запас снизу, чтобы подпись ролика
  // не закрывала его нижние строки. Рамку убираем до прокрутки, иначе она
  // висит на месте, пока страница едет.
  const load = page.locator('[data-tour="rp-load"]');
  await load.evaluate((el) => {
    el.style.marginBottom = '160px';
  });
  await page.evaluate(() => window.__director?.ring(null));
  await d.caption('Внизу — загрузка каждого сотрудника по дням');
  await load.evaluate((el) => el.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  await d.pause(1000);
  await d.show(load);
  await d.pause(2200);

  await d.caption('Готово', 2200);
  await d.save('resource-plan-build');
});
