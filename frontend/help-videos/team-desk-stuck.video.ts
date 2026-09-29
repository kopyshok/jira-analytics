// Ролик «Как разобрать зависшие задачи»: Стол тимлида → лента «Требует
// внимания» → отметить замечание «просмотрено» → задача ушла из списка.
// Если в демо-данных нет ни одного замечания — запасной сценарий: отбор
// по спринту и разбор очереди разработчика.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

type FlagCode =
  | 'over' | 'under' | 'decomp' | 'childgap' | 'orphan' | 'alien'
  | 'noest' | 'nospent' | 'idlespent' | 'stale';

const FLAG_LABELS: Record<FlagCode, string> = {
  over: 'Перерасход',
  under: 'Недорасход',
  decomp: 'Без декомпозиции',
  childgap: 'Подзадачи недооценены',
  orphan: 'Подзадача без родителя',
  alien: 'Часы другого разработчика',
  noest: 'Нет оценки',
  nospent: 'Нет списаний',
  idlespent: 'Часы в неначатой',
  stale: 'Зависла',
};

const FLAG_ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟', orphan: '⚠', alien: '⇄',
  noest: '∅', nospent: '◔', idlespent: '⏱', stale: '⏳',
};

// «Зависла» — по названию ролика; остальные признаки — запасной вариант,
// если именно зависших задач в демо-данных не окажется.
const FLAG_PRIORITY: FlagCode[] = [
  'stale', 'over', 'noest', 'nospent', 'decomp', 'idlespent', 'under', 'childgap', 'orphan', 'alien',
];

const TEAM = 'Команда Альфа';

interface Overview {
  flag_counts: Partial<Record<FlagCode, number>>;
  developers: { developer_id: string; display_name: string | null; total_issues: number }[];
  issues: { sprint: string | null }[];
}

test('team-desk-stuck', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);

  // Шапка раздела — свой профиль, отдельный от глобального фильтра команды.
  // Лишние колонки скрыты: список из 13 столбцов не помещается по ширине,
  // и наведение на значок замечания в правом крае уводит таблицу вбок —
  // ключ и название задачи слева пропадают из кадра.
  const filterRes = await page.request.put(`${api}/api/v1/users/me/team-desk-filter`, {
    data: {
      teams: [TEAM], mode: 'open', show_reviewed: false,
      show_done_subtasks: true, group_by_developer: true,
      hidden_columns: ['sprint', 'release', 'daily_rate', 'scale', 'days'],
    },
  });
  expect(filterRes.ok()).toBeTruthy();

  const overviewRes = await page.request.get(
    `${api}/api/v1/team-desk/overview`
    + `?teams=${encodeURIComponent(TEAM)}&only_open=true&show_reviewed=false&show_done_subtasks=true`,
  );
  expect(overviewRes.ok()).toBeTruthy();
  const overview = (await overviewRes.json()) as Overview;
  const flagCode = FLAG_PRIORITY.find((f) => (overview.flag_counts[f] ?? 0) > 0) ?? null;

  const issuesBlock = page.locator('[data-tour="desk-issues"]');

  if (flagCode) {
    const label = FLAG_LABELS[flagCode];
    const icon = FLAG_ICON[flagCode];
    const countBefore = overview.flag_counts[flagCode]!;

    await d.open('/team-desk', 'Как разобрать зависшие задачи');
    await expect(issuesBlock).toBeVisible({ timeout: 20_000 });
    // Лента «Требует внимания» показывает счётчик через « · N» — у чипа
    // «Отобрано» (ActiveFilters) той же подписи счётчика нет, различаем по нему.
    const flagBar = page.locator('[data-tour="desk-flags"] .ant-tag', { hasText: new RegExp(`${label} ·`) });
    await expect(flagBar).toBeVisible();
    await d.pause(800);
    await d.poster();
    await d.pause(1500);

    await d.caption(`Лента «Требует внимания» — тут задачи с замечанием «${label}»`);
    await d.show(flagBar);
    await d.pause(1000);

    await d.click(flagBar, `Отфильтруйте по замечанию «${label}»`);
    // Список задач перестраивается под фильтр — даём вёрстке улечься перед
    // тем, как наводить курсор на конкретную строку.
    await d.pause(500);

    const flagTag = issuesBlock.getByText(icon, { exact: true }).first();
    await expect(flagTag).toBeVisible();
    await d.click(flagTag, 'Нажмите на значок замечания у задачи');

    const menuItem = page.locator('.ant-dropdown-menu-item', { hasText: 'Просмотрено' });
    await d.click(menuItem, 'Выберите «Просмотрено»');

    const modal = page.locator('.ant-modal', { hasText: 'Просмотрено' });
    await expect(modal).toBeVisible();
    await d.pause(400);
    await d.click(modal.getByRole('button', { name: 'Отметить' }), 'Подтвердите');
    await expect(modal).toBeHidden();
    // Настоящая мышь осталась над лентой — уводим, чтобы не всплывали подсказки.
    await page.mouse.move(1100, 180);

    if (countBefore - 1 > 0) {
      await expect(flagBar).toContainText(`· ${countBefore - 1}`);
    } else {
      await expect(flagBar).toHaveCount(0);
    }

    await d.caption('Замечание снято — задача ушла из списка проблемных');
    await d.show(countBefore - 1 > 0 ? flagBar : page.locator('[data-tour="desk-flags"]'));
    await d.pause(1400);

    await d.caption('Готово', 2200);
    await d.save('team-desk-stuck');
    return;
  }

  // Запасной сценарий: замечаний в демо-данных нет — показываем отбор по
  // спринту и разбор очереди конкретного разработчика.
  const sprint = overview.issues.map((i) => i.sprint).find((s): s is string => Boolean(s));
  const developer = overview.developers.find((dv) => dv.total_issues > 0 && dv.display_name);

  await d.open('/team-desk', 'Как посмотреть задачи разработчика по спринту');
  await expect(issuesBlock).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  if (sprint) {
    const sprintSelect = page.locator('[data-tour="desk-filters"] .ant-select').filter({
      has: page.locator('.ant-select-selection-placeholder', { hasText: 'Все спринты' }),
    });
    await d.click(sprintSelect, 'Отберите задачи по спринту');
    const option = page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: sprint });
    await d.click(option);
    await page.keyboard.press('Escape');
  }

  if (developer) {
    const card = page.locator('.ant-card', { hasText: developer.display_name! }).first();
    await d.click(card, `Откройте очередь разработчика «${developer.display_name}»`);
  }

  await expect(issuesBlock).toBeVisible();
  await d.caption('Видно, какие задачи у него в работе');
  await d.show(issuesBlock);
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('team-desk-stuck');
});
