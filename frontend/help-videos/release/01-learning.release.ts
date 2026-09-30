// Глава «Ролики в справке и «Первые шаги»»: кнопка «Первые шаги» в шапке, панель
// с настройкой команды и экскурсиями, ролик у шага, экскурсия по шапке и блок
// «Видео» в справке раздела. Всё на одной странице — ресурсном плане демо-команды.
import { expect, test } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';
import { plural } from './slides.ts';

// Сколько роликов в справке — по реестру приложения (сам реестр в Node не импортируется).
const VIDEO_COUNT = (
  readFileSync(new URL('../../src/help-videos/videos.ts', import.meta.url), 'utf-8').match(/\bvideo\('/g) ?? []
).length;

const TEAM = 'Команда Альфа';

type Status = { me: { completed_tours: string[] } };
type Scenario = { id: string; quarter: string | null; year: number | null };
type Plan = { id: string; scenario_id: string | null };

releaseFrame();

let planId = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string, params?: Record<string, string>): Promise<T> => {
    const res = await request.get(url, { params });
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  // Шапка — на демо-команду (предыдущие главы могли переключить).
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Панель «Первые шаги» не скрыта и не всплывает сама (открываем кнопкой);
  // экскурсия по шапке ещё не пройдена — у пункта кнопка «Показать».
  const { me } = await getJson<Status>(`${api}/onboarding/status`, { team: TEAM });
  const put = await request.put(`${api}/onboarding/me`, {
    data: { hidden: false, auto_opened: true, completed_tours: me.completed_tours.filter((t) => t !== 'header') },
  });
  expect(put.ok()).toBeTruthy();

  // Фон главы — ресурсный план последнего утверждённого сценария команды.
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`, { status: 'approved', teams: TEAM });
  const scenario = scenarios
    .filter((s) => s.quarter && s.year)
    .sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`))
    .at(-1);
  expect(scenario, `нет утверждённого сценария команды ${TEAM}`).toBeTruthy();
  const plans = await getJson<Plan[]>(`${api}/resource-planning/resource-plans`, { team: TEAM });
  const plan = plans.find((p) => p.scenario_id === scenario!.id);
  expect(plan, 'нет ресурсного плана утверждённого сценария').toBeTruthy();
  planId = plan!.id;
  await request.dispose();
});

test('01-learning', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/resource-planning?plan_id=${planId}`, chapterTitle('Ролики в справке и «Первые шаги»'));

  const button = page.getByTestId('onboarding-button');
  await expect(button).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-tour="rp-gantt"]')).toBeVisible({ timeout: 60_000 });
  await d.pause(1500);

  // «Первые шаги»: кнопка с прогрессом → панель с настройкой команды.
  await d.click(button, 'В шапке — «Первые шаги» и сколько уже пройдено');
  const drawer = page.getByRole('dialog', { name: 'Первые шаги' });
  const setupTitle = drawer.getByRole('heading', { name: 'Настройка команды' });
  const absences = drawer.getByTestId('onboarding-step-absences');
  await expect(setupTitle).toBeVisible();
  await d.caption('Настройка команды — общая, отметки ставятся по данным');
  await d.show(setupTitle, absences);
  await d.pause(700);

  // Ролик у шага: окно с роликом играет несколько секунд.
  await d.click(absences.getByRole('button', { name: 'Видео', exact: true }), 'У шага — короткий ролик, как это сделать');
  const modal = page.getByRole('dialog', { name: 'Как внести отпуск' });
  const video = modal.locator('video');
  await expect(video).toBeVisible();
  await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.currentTime), { timeout: 10_000 }).toBeGreaterThan(0.2);
  // Пока играет ролик, своя подпись не нужна — у ролика внутри свои подписи.
  await page.evaluate(() => document.querySelector('#__director .d-caption')?.classList.remove('show'));
  await page.mouse.move(1900, 60);
  await d.pause(2000);
  await d.click(modal.locator('.ant-modal-close'));
  await expect(modal).toBeHidden();

  // Экскурсии: пункт «Шапка» — подсветка первого шага и выход.
  const introTitle = drawer.getByRole('heading', { name: 'Знакомство с сервисом' });
  await d.caption('Знакомство с сервисом — экскурсии по разделам');
  await d.show(introTitle, drawer.getByTestId('tour-start-team-desk'));
  await d.pause(600);
  await d.click(drawer.getByTestId('tour-start-header'));
  const tour = page.locator('.ant-tour:visible');
  await expect(tour).toContainText('Команда', { timeout: 15_000 });
  await d.caption('Экскурсия подсвечивает, что где на экране');
  await d.pause(1500);
  await d.click(tour.locator('.ant-tour-close'));
  await expect(tour).toBeHidden();

  // Справка раздела: блок «Видео» с карточками роликов.
  await d.click(page.locator('[data-tour="header-help"] button'), 'В справке раздела — блок «Видео»');
  const help = page.getByRole('dialog', { name: 'Планирование ресурсов' });
  const videosTitle = help.getByRole('heading', { name: 'Видео', exact: true });
  await expect(videosTitle).toBeVisible();
  await videosTitle.evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  await d.pause(900);
  const cards = help.getByRole('button', { name: /^Смотреть видео:/ });
  const videos = `${VIDEO_COUNT} ${plural(VIDEO_COUNT, 'короткий ролик', 'коротких ролика', 'коротких роликов')}`;
  await d.caption(`${videos} — в справке разделов и «Первых шагах»`);
  await d.show(cards.nth(0), cards.nth(2));
  await d.pause(2500);
  await saveClip(d, '01-learning');
});
