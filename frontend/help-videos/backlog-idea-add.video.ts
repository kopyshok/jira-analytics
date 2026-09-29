// Ролик «Как завести идею и связать её с Jira»: Целевые задачи → «Идея вручную» →
// название, команда, оценки по ролям → в строке — заказчик, аналитик, разработчик,
// приоритет → «Связать с Jira» с уже загруженной задачей → идея стала задачей.
import { expect, test, type APIRequestContext, type Locator } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const TITLE = 'Отчёт по остаткам на складе';

interface RootNode {
  id: string;
  key: string;
  status: string;
  status_category: string | null;
  is_container: boolean;
  is_context: boolean;
  has_children: boolean;
  category: string | null;
}
type BacklogRow = { id: string; title: string; issue_id: string | null };

/** Задача Jira, уже загруженная синхронизацией, но ещё ни с одной идеей не связанная —
 *  на ней ролик показывает «Связать с Jira» без похода в настоящую Jira. Берём
 *  корневые узлы «Категорий задач» с primary_only=true — иначе можно наткнуться на
 *  задачу чужой команды, у которой наша лишь «участвует» (backlog фильтрует по
 *  продуктовой команде задачи и такую бы не показал после привязки). */
async function findUnlinkedIssueKeys(request: APIRequestContext, api: string): Promise<string[]> {
  const linked = new Set<string>();
  for (const view of ['active', 'archived', 'quarterly'] as const) {
    const rows: BacklogRow[] = await (
      await request.get(`${api}/backlog`, { params: { view } })
    ).json();
    for (const r of rows) if (r.issue_id) linked.add(r.issue_id);
  }
  const candidates: RootNode[] = [];
  for (const tab of ['active', 'stack'] as const) {
    const nodes: RootNode[] = await (
      await request.get(`${api}/issues/tree/roots`, { params: { teams: TEAM, tab } })
    ).json();
    candidates.push(...nodes);
  }
  // «Бэклог» — это инициативы (Эпики/RFA), а не рядовые задачи: обычная
  // «Задача» после привязки в списке не появится (отфильтрована как leaf).
  // Берём контейнерный узел (is_container) без потомков — простая строка без
  // раскрытия дерева; выполненные/отменённые «Бэклог» тоже скрывает.
  const usable = candidates.filter(
    (n) =>
      n.key && n.is_container && !n.is_context && !n.has_children && !linked.has(n.id)
      && n.status_category !== 'done' && !/отмен|cancel|rejected|won.?t do/i.test(n.status),
  );
  if (usable.length === 0) throw new Error(`Нет свободной задачи Jira для привязки в команде ${TEAM}`);
  // На случай расхождений в данных демо-базы отдаём несколько кандидатов —
  // ролик пробует их по очереди, пока привязка не пройдёт.
  return usable.slice(0, 8).map((n) => n.key);
}

let targetKeys: string[] = [];
let createdId: string | null = null;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  targetKeys = await findUnlinkedIssueKeys(request, api);
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  if (!createdId) return;
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.delete(`${api}/backlog/${createdId}`);
  await request.dispose();
});

test('backlog-idea-add', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Боковая ссылка «Целевые задачи» ведёт на голый /backlog (без ?view=) — открываем
  // так и переключаемся на «Бэклог» кликом по вкладке, а не query-параметром в URL,
  // иначе редундантный клик по разделу в кадре сбросил бы вкладку обратно.
  await d.open('/backlog', 'Как завести идею и связать её с Jira');
  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Откройте раздел «Целевые задачи»');
  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }),
    'Перейдите на вкладку «Бэклог»',
  );
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();

  await d.click(page.locator('[data-tour="backlog-manual-idea"]'), 'Нажмите «Идея вручную»');
  const modal = page.locator('.ant-modal', { hasText: 'Новая идея' });
  await expect(modal).toBeVisible();

  const field = (label: string) => modal.locator('.ant-form-item', { hasText: label }).last();
  await d.type(field('Название').locator('input'), TITLE, 'Название — своими словами, задачи в Jira ещё нет');
  await d.click(field('Команда').locator('.ant-select'), 'Выберите команду');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: new RegExp(`^${TEAM}$`) }));
  await d.type(field('АН ч').locator('input'), '24', 'Оцените часы по ролям');
  await d.type(field('ПР ч').locator('input'), '80', 'Разработка');
  await d.type(field('ТС ч').locator('input'), '16', 'И тестирование');

  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните');
  await expect(modal).toBeHidden();

  const newRow = pane.locator('tbody tr', { hasText: TITLE });
  await expect(newRow).toBeVisible({ timeout: 20_000 });

  // Дальше идею находим и правим по её собственному id — так надёжнее, чем по тексту:
  // после привязки к Jira название в строке сменится.
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  const created: BacklogRow[] = await (
    await page.request.get(`${api}/backlog`, { params: { view: 'active', teams: TEAM } })
  ).json();
  const item = created.find((it) => it.title === TITLE);
  if (!item) throw new Error('Идея не найдена после создания');
  createdId = item.id;

  const row = pane.locator(`tr[data-row-key="${createdId}"]`);
  const cell = (i: number) => row.locator('td').nth(i);

  await d.type(cell(4).locator('input[placeholder="Заказчик…"]'), 'Заказчик 1', 'В строке — заказчик');

  const analystSelect: Locator = cell(2).locator('.ant-select');
  await d.click(analystSelect, 'Аналитик');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option').first());

  const devSelect: Locator = cell(3).locator('.ant-select');
  await d.click(devSelect, 'И разработчик');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option').first());

  await page.mouse.move(1100, 160);
  await d.type(cell(0).locator('input'), '3', 'Приоритет — чем меньше число, тем выше идея в списке');

  await page.mouse.move(1100, 160);
  await d.click(row.locator('[data-tour="backlog-link-jira"]'), 'Когда задача появится в Jira — свяжите её с идеей');
  const linkModal = page.locator('.ant-modal', { hasText: 'Связать идею с Jira-задачей' });
  await expect(linkModal).toBeVisible();
  await d.caption('Jira подставит своё название, часы и приоритизацию');
  await d.show(linkModal.locator('.ant-alert'));

  const jiraKeyInput = linkModal.locator('#jira_key');
  let linkedKey = '';
  for (const [i, key] of targetKeys.entries()) {
    if (i === 0) await d.type(jiraKeyInput, key, 'Укажите ключ задачи');
    else {
      await jiraKeyInput.click();
      await jiraKeyInput.press('Control+A');
      await jiraKeyInput.pressSequentially(key, { delay: 60 });
    }
    await d.click(linkModal.locator('.ant-modal-footer .ant-btn-primary'), i === 0 ? 'Свяжите' : undefined);
    await d.pause(900);
    if (!(await linkModal.isVisible())) { linkedKey = key; break; }
    // Редкая задача уже связана другой идеей в базе — пробуем следующую,
    // не покидая окно.
    const notice = page.locator('.ant-notification-notice');
    await notice.locator('.ant-notification-notice-close').first().click().catch(() => {});
  }
  if (!linkedKey) throw new Error('Не удалось связать ни с одной из подготовленных задач');

  const linkedRow = pane.locator('tbody tr', { hasText: linkedKey });
  await expect(linkedRow).toBeVisible({ timeout: 20_000 });
  await page.mouse.move(1100, 160);
  await d.caption('Идея стала задачей Jira — и готова попасть в «Сценарии» квартала');
  await d.show(linkedRow);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('backlog-idea-add');
});
