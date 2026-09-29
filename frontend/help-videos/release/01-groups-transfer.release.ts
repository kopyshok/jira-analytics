// Глава 1 «Группы: перевод и деление сотрудника»: «Ресурсы» команды с группами →
// группа в строке сотрудника → карточка → блок «Группы» → деление 60/40 с даты →
// окно перевода в другую группу (объясняет, зачем дата).
// Красной плашки «Без группы» в демо-данных нет: у всех активных участников
// команды группа есть, поэтому в главе её не показываем.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { CHAPTERS } from './chapters.ts';
import { chapterTitle, hideVersion, releaseFrame, saveClip } from './common.ts';

/** Сотрудник команды с группами, которого делим и переводим (демо-база). */
const PERSON = 'Ольховская Раиса';

type Team = { name: string; has_subgroups: boolean; subgroups: { id: string; name: string }[] };
type Employee = { id: string; display_name: string };
type ShareRecord = { valid_from: string | null; shares: { subgroup_id: string; percent: number }[] };

releaseFrame();

let team = '';
let fromGroup = '';
let toGroup = '';

// Данные готовим до открытия окна: запись идёт с момента его создания.
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

  // Команда с делением на группы — в демо-базе она одна.
  const registry = await getJson<Team[]>(`${api}/teams/registry`);
  const withGroups = registry.find((t) => t.has_subgroups && t.subgroups.length >= 2);
  expect(withGroups, 'нет команды с группами').toBeTruthy();
  team = withGroups!.name;
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [team], subgroups: [] } })).ok()).toBeTruthy();

  const employees = await getJson<Employee[]>(`${api}/employees`);
  const person = employees.find((e) => e.display_name === PERSON);
  expect(person, `нет сотрудника ${PERSON}`).toBeTruthy();

  // Исходная картина: только запись «с начала участия». Записи с датой (от прошлых
  // прогонов в той же копии базы) удаляем — в ролике их создают заново.
  const sharesUrl = `${api}/teams/employees/${person!.id}/subgroup-shares`;
  let history = await getJson<ShareRecord[]>(`${sharesUrl}?team=${encodeURIComponent(team)}`);
  for (const r of history.filter((x) => x.valid_from)) {
    const res = await request.delete(sharesUrl, { params: { team, valid_from: r.valid_from! } });
    expect(res.ok()).toBeTruthy();
  }
  history = await getJson<ShareRecord[]>(`${sharesUrl}?team=${encodeURIComponent(team)}`);
  const base = history.find((r) => r.valid_from === null);
  expect(base?.shares.length, 'у сотрудника должна быть одна группа с начала участия').toBe(1);
  const byId = new Map(withGroups!.subgroups.map((g) => [g.id, g.name]));
  fromGroup = byId.get(base!.shares[0].subgroup_id)!;
  toGroup = withGroups!.subgroups.find((g) => g.name !== fromGroup)!.name;
  await request.dispose();
});

test('01-groups-transfer', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await hideVersion(page);
  await d.open('/capacity', chapterTitle(1, CHAPTERS[0]));

  const row = page.locator('tbody tr.capacity-emp-row', { hasText: PERSON });
  const groupLink = row.locator('a', { hasText: fromGroup });
  await expect(groupLink).toBeVisible({ timeout: 60_000 });
  await d.pause(1200);

  await d.caption('У команды с группами группа видна в строке сотрудника');
  await d.show(groupLink);
  await d.pause(700);

  await d.click(groupLink, 'В карточке сотрудника — новый блок «Группы»');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  const groups = drawer.getByText('Группы', { exact: true }).locator('xpath=..');
  await expect(groups.getByText('с начала участия')).toBeVisible({ timeout: 20_000 });
  await d.show(groups);
  await d.pause(900);

  // Деление: 60 % в своей группе, 40 % — в соседней.
  await d.click(groups.getByRole('button', { name: 'Разделить между группами' }), 'Время можно разделить между группами');
  const split = page.locator('.ant-modal', { hasText: 'Разделить между группами' });
  await expect(split).toBeVisible();
  const pctInput = (name: string) =>
    split.locator('.ant-space').filter({ has: page.locator('span', { hasText: new RegExp(`^${name}$`) }) }).last().locator('input');
  // Проценты вводятся подряд, без долгой паузы у каждого поля.
  const typePct = async (name: string, value: string) => {
    await d.point(pctInput(name));
    await pctInput(name).click();
    await pctInput(name).pressSequentially(value, { delay: 90 });
  };
  await d.caption('Доли в процентах — в сумме 100');
  await typePct(fromGroup, '60');
  await typePct(toGroup, '40');
  await expect(split.getByText('Итого 100%')).toBeVisible();
  await d.pause(500);
  await d.click(split.getByRole('button', { name: 'Сохранить' }));
  await expect(split).toBeHidden();
  const splitLine = groups.locator(':scope > div', { hasText: '60%' });
  await expect(splitLine).toBeVisible();
  await page.mouse.move(700, 120);
  await d.caption('С этой даты — 60% в одной группе и 40% в другой');
  await d.show(splitLine);
  await d.pause(1200);

  // Перевод целиком: окно то же, дата обязательна — окно объясняет почему.
  // Сам перевод не сохраняем: дата по умолчанию совпала бы с датой деления.
  await d.click(groups.getByRole('button', { name: 'Перевести в группу' }), 'Перевод в другую группу — тоже только с даты');
  const transfer = page.locator('.ant-modal', { hasText: 'Новая группа' });
  await expect(transfer).toBeVisible();
  await d.caption('Окно объясняет, почему нужна дата');
  await d.show(transfer.getByText(/^Запись «с начала участия» уже есть/));
  await d.pause(1100);
  await d.click(transfer.getByRole('button', { name: 'Отмена' }));
  await expect(transfer).toBeHidden();
  await page.mouse.move(700, 120);

  await d.caption('Прошлое не меняется: до даты часы — в прежней группе');
  await d.show(groups);
  await d.pause(2700);
  await saveClip(page, '01-groups-transfer');
});
