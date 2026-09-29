// Ролик «Как настроить роли и рабочий стол аналитика»: Ресурсы → вкладка
// «Роли» (роль, «В планировании») → вкладка «Рабочие столы»: создать ссылку
// для аналитика → открыть стол по ссылке → виджеты → вернуться →
// «Перевыпустить» / «Отозвать» → вкладка «Команда»: выгрузка в Excel.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const ANALYST = 'Акимова Алина';
const ROLE_CODE = 'consultant-video';
const ROLE_LABEL = 'Видео-консультант';

test('capacity-roles-desks', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  await d.open('/capacity', 'Как настроить роли и рабочий стол аналитика');
  await expect(page.locator('[data-tour="capacity-team-table"] tbody tr.capacity-emp-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');

  // === Вкладка «Роли» ===
  await d.click(page.getByRole('tab', { name: 'Роли' }), 'Перейдите на вкладку «Роли»');
  const activePane = page.locator('.ant-tabs-tabpane-active');
  await expect(activePane.locator('table').filter({ hasText: 'В планировании' })).toBeVisible();

  await d.click(page.getByRole('button', { name: 'Добавить роль' }), 'Добавьте новую роль');
  const roleModal = page.locator('.ant-modal', { hasText: 'Новая роль' });
  await expect(roleModal).toBeVisible();
  await d.type(roleModal.locator('#code'), ROLE_CODE, 'Внутренний код роли');
  await d.type(roleModal.locator('#label'), ROLE_LABEL, 'Название в списке у сотрудника');
  await d.click(roleModal.getByRole('button', { name: 'OK' }));
  await expect(roleModal).toBeHidden();

  const roleRow = activePane.locator('tr', { hasText: ROLE_LABEL });
  await expect(roleRow).toBeVisible();
  const planningSwitch = roleRow.getByRole('switch').first();
  await d.caption('«В планировании» решает, войдёт ли роль в ресурс сценария');
  await d.click(planningSwitch);
  await d.pause(700);
  await d.click(planningSwitch);
  await d.pause(500);

  // Роль учебная — убираем сразу, чтобы не путалась в списке у сотрудников.
  await d.click(roleRow.locator('.ant-tag').last(), 'Удалите — роль никому не назначена');
  const roleConfirm = page.locator('.ant-popconfirm:visible', { hasText: 'Удалить роль?' });
  await expect(roleConfirm).toBeVisible();
  await d.click(roleConfirm.getByRole('button', { name: 'Удалить' }));
  await expect(roleRow).toBeHidden();

  // === Вкладка «Рабочие столы» ===
  await d.click(page.getByRole('tab', { name: 'Рабочие столы' }), 'Перейдите на вкладку «Рабочие столы»');
  const deskRow = activePane.locator('tr', { hasText: ANALYST });
  await expect(deskRow).toBeVisible();
  await d.caption(`Выпустите стол аналитику: ${ANALYST}`);
  await d.show(deskRow);
  await d.pause(500);

  const [createResp] = await Promise.all([
    page.waitForResponse((r) => r.url().endsWith('/work-desks') && r.request().method() === 'POST'),
    (async () => {
      await d.click(deskRow.getByRole('button', { name: 'Создать' }), 'Нажмите «Создать»');
      const deskModal = page.locator('.ant-modal', { hasText: 'Новый стол' });
      await expect(deskModal).toBeVisible();
      await d.caption('Виджеты личного стола аналитика');
      await d.show(deskModal.locator('.ant-checkbox-group'));
      await d.click(deskModal.getByRole('button', { name: 'Создать' }));
    })(),
  ]);
  const desk: { token: string } = await createResp.json();

  await expect(deskRow.locator('.ant-tag', { hasText: 'Активен' })).toBeVisible();
  await d.click(deskRow.getByRole('button', { name: 'Копировать ссылку' }), 'Скопируйте ссылку — она без входа в систему');
  await expect(page.getByText('Ссылка скопирована')).toBeVisible();

  // Открываем стол по ссылке — в этом же окне.
  await page.goto(`/desk/${desk.token}`);
  await expect(page.locator('.desk-user-name', { hasText: ANALYST })).toBeVisible({ timeout: 15_000 });
  await page.mouse.move(900, 120);
  await d.caption('Так стол выглядит у самого сотрудника');
  await d.show(page.locator('.desk-layout'));
  await d.pause(1600);

  // Возвращаемся в «Ресурсы» → «Рабочие столы».
  await page.goto('/capacity');
  await expect(page.locator('[data-tour="capacity-team-table"] tbody tr.capacity-emp-row').first()).toBeVisible();
  await d.click(page.getByRole('tab', { name: 'Рабочие столы' }), 'Вернитесь к списку столов');
  const deskRow2 = activePane.locator('tr', { hasText: ANALYST });
  await expect(deskRow2).toBeVisible();

  await d.click(deskRow2.getByRole('button', { name: 'Перевыпустить' }), 'Ссылка попала не к тому? «Перевыпустить» — старая перестанет работать');
  const regenConfirm = page.locator('.ant-popconfirm:visible', { hasText: 'Перевыпустить стол?' });
  await expect(regenConfirm).toBeVisible();
  await d.click(regenConfirm.getByRole('button', { name: 'Перевыпустить' }));
  await expect(page.getByText('Стол перевыпущен')).toBeVisible();

  await d.click(deskRow2.getByRole('button', { name: 'Отозвать' }), 'А если стол больше не нужен — «Отозвать»');
  const revokeConfirm = page.locator('.ant-popconfirm:visible', { hasText: 'Отозвать стол?' });
  await expect(revokeConfirm).toBeVisible();
  await d.click(revokeConfirm.getByRole('button', { name: 'Отозвать' }));
  await expect(page.getByText('Стол отозван')).toBeVisible();
  await expect(deskRow2.locator('.ant-tag', { hasText: 'Нет' })).toBeVisible();
  await d.show(deskRow2);
  await d.pause(1200);

  // === Вкладка «Команда»: выгрузка в Excel ===
  await d.click(page.getByRole('tab', { name: 'Команда' }), 'На вкладке «Команда» есть выгрузка плана');
  const exportBtn = activePane.locator('a.ant-btn', { hasText: 'Экспорт в Excel' });
  await expect(exportBtn).toBeVisible();
  await d.caption('«Экспорт в Excel» выгрузит план и факт по всем командам');
  await d.point(exportBtn);
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('capacity-roles-desks');
});
