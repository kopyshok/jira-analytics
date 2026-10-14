import type {
  ApplySummary, FieldRow, HoursRow, JobKind, PersonRow, PersonSource, PersonStatus,
} from '../api/jiraMigration';

export const PERSON_STATUS_LABEL: Record<PersonStatus, string> = {
  by_hours: 'По списаниям',
  by_name: 'По ФИО',
  disputed: 'Спорно',
  not_found: 'Не найден',
  search_failed: 'Поиск не удался',
};

export const PERSON_STATUS_COLOR: Record<PersonStatus, string> = {
  by_hours: 'green',
  by_name: 'blue',
  disputed: 'orange',
  not_found: 'red',
  search_failed: 'red',
};

export const PERSON_SOURCE_LABEL: Record<PersonSource, string> = {
  auto: 'Подобрано автоматически',
  decision: 'Выбрано администратором',
  none: 'Без привязки',
  conflict: 'Конфликт: этого пользователя занял другой сотрудник',
};

export const JOB_KIND_LABEL: Record<JobKind, string> = {
  dry_run: 'Пробный прогон',
  apply: 'Применение переезда',
  full_sync: 'Полная синхронизация',
};

// Те же подписи, что в истории запусков на странице синхронизации; «interrupted» — только здесь.
export const SYNC_STATUS_LABEL: Record<string, string> = {
  ok: 'Успешно',
  partial: 'Частично',
  failed: 'Ошибка',
  cancelled: 'Прерван',
  interrupted: 'Прервана перезапуском сервиса',
  running: 'Выполняется',
  skipped: 'Пропущен',
};

export const SYNC_STATUS_COLOR: Record<string, string> = {
  ok: 'success',
  partial: 'warning',
  failed: 'error',
  cancelled: 'default',
  interrupted: 'error',
  running: 'processing',
  skipped: 'default',
};

export const REPORT_STATUS_LABEL: Record<string, string> = {
  running: 'Выполняется',
  done: 'Готов',
  failed: 'Не удался',
};

/** Счётчики хода операции (приходят с сервера под служебными ключами). */
export const COUNTER_LABEL: Record<string, string> = {
  issues_read: 'Прочитано задач',
  worklogs_read: 'Прочитано списаний',
  people_checked: 'Проверено сотрудников',
};

/** Строки итога применения: ключ → подпись. Порядок — как показывать. */
export const APPLY_SUMMARY_ROWS: ReadonlyArray<readonly [string, string]> = [
  ['settings', 'Настроек полей переписано'],
  ['projects', 'Проектов перепривязано'],
  ['issues_rebound', 'Задач перепривязано'],
  ['issues_deleted', 'Задач удалено'],
  ['plan_sources', 'Источников плановых часов переписано'],
  ['choices_dropped', 'У задач сброшен выбор оценки'],
  ['employees_bound', 'Сотрудников привязано'],
  ['employees_unbound', 'Сотрудников оставлено без привязки'],
  ['people_refs', 'Ссылок на людей переписано'],
  ['kpi_payload_skipped', 'Записей KPI пропущено'],
  ['worklogs_deleted', 'Списаний удалено (вернутся полной синхронизацией)'],
  ['worklogs_kept', 'Списаний сохранено (задачи остались без изменений)'],
  ['comments_deleted', 'Комментариев удалено (после переезда сервис их не загружает)'],
  ['comments_kept', 'Комментариев сохранено (задачи остались без изменений)'],
];

/** Места, где переписаны ссылки на людей (разбивка строки «Ссылок на людей переписано»). */
const PEOPLE_REFS_LABEL: Record<string, string> = {
  issues_assignee: 'исполнители задач',
  issues_reporter: 'авторы задач',
  issues_developer: 'разработчики задач',
  backlog_assignee_at_choice: 'исполнители в бэклоге при выборе оценки',
  users_team_desk_filter: 'фильтры стола тимлида',
  kpi_approvals: 'утверждённые KPI',
};

export interface ApplySummaryItem {
  key: string;
  label: string;
  value: number;
  detail: string | null;
}

/** Итог применения для показа: только известные строки; разбивка — без нулей и без незнакомых мест. */
export function applySummaryItems(summary: ApplySummary): ApplySummaryItem[] {
  const items: ApplySummaryItem[] = [];
  for (const [key, label] of APPLY_SUMMARY_ROWS) {
    const raw = summary[key];
    if (typeof raw === 'number') {
      items.push({ key, label, value: raw, detail: null });
    } else if (raw && typeof raw === 'object') {
      const parts = Object.entries(raw as Record<string, unknown>)
        .filter((entry): entry is [string, number] => typeof entry[1] === 'number');
      const detail = parts
        .filter(([part, n]) => n > 0 && part in PEOPLE_REFS_LABEL)
        .map(([part, n]) => `${PEOPLE_REFS_LABEL[part]} — ${n.toLocaleString('ru-RU')}`)
        .join(', ');
      items.push({ key, label, value: parts.reduce((sum, [, n]) => sum + n, 0), detail: detail || null });
    }
  }
  return items;
}

/**
 * Предложить запустить полную синхронизацию после переезда заново: сейчас ничего
 * не идёт, а последний запуск не завершился успешно (упал, прерван, не стартовал).
 */
export function offerFullSyncRestart(job: { state: string }, run: { status: string } | null): boolean {
  if (job.state === 'running' || run?.status === 'running') return false;
  return run?.status !== 'ok';
}

/** Пользователь новой Jira в списке выбора: ФИО (логин), почта, пометка «неактивен». */
export function dcUserLabel(user: {
  display_name: string; name: string | null; email?: string | null; active?: boolean;
}): string {
  const email = user.email ? `, ${user.email}` : '';
  const inactive = user.active === false ? ' — неактивен' : '';
  return `${candidateLabel(user)}${email}${inactive}`;
}

/** «1 совпавшее списание», «3 совпавших списания», «12 совпавших списаний». */
export function matchedWorklogsLabel(n: number): string {
  const d = n % 10;
  const dd = n % 100;
  if (d === 1 && dd !== 11) return `${n} совпавшее списание`;
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return `${n} совпавших списания`;
  return `${n} совпавших списаний`;
}

/** Счётчики хода операции с подписями; без подписи — не показываются. */
export function counterLines(counters: Record<string, number>): string[] {
  return Object.entries(counters)
    .filter(([key]) => key in COUNTER_LABEL)
    .map(([key, value]) => `${COUNTER_LABEL[key]}: ${value.toLocaleString('ru-RU')}`);
}

export type PeopleFilter = 'attention' | 'all' | 'by_hours' | 'by_name' | 'unbound';

export function fieldStatus(row: FieldRow): { label: string; color: string } {
  if (row.decision) {
    return row.decision.dc_field_id
      ? { label: 'Выбрано вручную', color: 'blue' }
      : { label: 'Не используется', color: 'default' };
  }
  if (row.suggested_id) return { label: 'Совпало по названию', color: 'green' };
  if (row.auto_only) return { label: 'Найдётся само', color: 'default' };
  return { label: 'Нужно решение', color: 'red' };
}

export function candidateLabel(user: { display_name: string; name: string | null }): string {
  return user.name ? `${user.display_name} (${user.name})` : user.display_name;
}

export function personBindingText(row: PersonRow): string {
  const final = row.final;
  if (!final || !final.key) return final?.unresolved ? 'Нужно решение' : 'Без привязки';
  return candidateLabel({ display_name: final.display_name ?? final.key, name: final.name });
}

export function filterPeople(rows: PersonRow[], filter: PeopleFilter): PersonRow[] {
  switch (filter) {
    case 'attention':
      return rows.filter((r) => r.final?.unresolved);
    case 'by_hours':
      return rows.filter((r) => r.status === 'by_hours');
    case 'by_name':
      return rows.filter((r) => r.status === 'by_name');
    case 'unbound':
      return rows.filter((r) => r.final && !r.final.unresolved && !r.final.key);
    default:
      return rows;
  }
}

/**
 * Часы, которые уйдут от карточки сотрудника: он без привязки (или решение не принято), а его
 * списания на перенесённых задачах полная синхронизация привяжет к новой карточке без команды.
 */
export function hoursLeaving(row: PersonRow): number {
  if (!row.final || row.final.key) return 0;
  return row.hours_at_risk ?? 0;
}

export function totalHoursLeaving(rows: PersonRow[]): number {
  return rows.reduce((sum, row) => sum + hoursLeaving(row), 0);
}

export function formatHours(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
}

export function formatDiff(row: HoursRow): string {
  if (row.db_hours === 0 && row.dc_hours === 0) return '—';
  const value = Math.abs(row.diff_pct).toLocaleString('ru-RU', { maximumFractionDigits: 1 });
  const sign = row.diff_pct > 0 ? '+' : row.diff_pct < 0 ? '−' : '';
  return `${sign}${value} %`;
}

export function fmtDateTime(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString('ru-RU') : '—';
}

/** Интервал опроса состояния, мс; `false` — не опрашивать. Полная синхронизация длится долго — реже. */
export function pollInterval(data: {
  job: { state: string; kind: string | null };
  sync_run: { status: string } | null;
} | undefined): number | false {
  if (!data) return false;
  if (data.job.state === 'running') return data.job.kind === 'full_sync' ? 15000 : 2000;
  if (data.sync_run?.status === 'running') return 15000;
  return false;
}
