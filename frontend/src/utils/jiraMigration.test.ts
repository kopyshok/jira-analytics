import { describe, expect, it } from 'vitest';
import type { FieldRow, HoursRow, PersonFinal, PersonRow } from '../api/jiraMigration';
import {
  applySummaryItems, candidateLabel, counterLines, dcUserLabel, fieldStatus, filterPeople, formatDiff,
  hoursLeaving, matchedWorklogsLabel, totalHoursLeaving,
  offerFullSyncRestart, personBindingText, pollInterval, PERSON_STATUS_LABEL, SYNC_STATUS_LABEL,
} from './jiraMigration';

const field = (over: Partial<FieldRow> = {}): FieldRow => ({
  cloud_id: 'customfield_1', cloud_name: 'Поле', labels: [], suggested_id: null,
  suggested_name: null, decision: null, final_id: null, final_name: null,
  auto_only: false, unresolved: true, ...over,
});

const final = (over: Partial<PersonFinal> = {}): PersonFinal => ({
  key: null, name: null, display_name: null, source: 'none', unresolved: false, note: null, ...over,
});

const person = (over: Partial<PersonRow> = {}): PersonRow => ({
  employee_id: 'e1', display_name: 'Иванов Иван', worklogs: 0, matched: 0,
  status: 'not_found', candidates: [], auto: null, decision: null, final: null, ...over,
});

const hours = (over: Partial<HoursRow> = {}): HoursRow => ({
  team: 'Команда А', month: '2026-09', db_hours: 10, dc_hours: 10, diff_pct: 0,
  flagged: false, ...over,
});

describe('fieldStatus', () => {
  it('ручное решение', () => {
    expect(fieldStatus(field({ decision: { dc_field_id: 'customfield_2' } })).label).toBe('Выбрано вручную');
    expect(fieldStatus(field({ decision: { dc_field_id: null } })).label).toBe('Не используется');
  });
  it('предложение, автопоиск и нужно решение', () => {
    expect(fieldStatus(field({ suggested_id: 'customfield_2' })).label).toBe('Совпало по названию');
    expect(fieldStatus(field({ auto_only: true })).label).toBe('Найдётся само');
    expect(fieldStatus(field()).label).toBe('Нужно решение');
  });
});

describe('personBindingText', () => {
  it('привязка с логином', () => {
    const row = person({ final: final({ key: 'JIRAUSER5', name: 'Ivanov_I', display_name: 'Иванов Иван', source: 'auto' }) });
    expect(personBindingText(row)).toBe('Иванов Иван (Ivanov_I)');
  });
  it('без привязки и нужно решение', () => {
    expect(personBindingText(person({ final: final({ source: 'decision' }) }))).toBe('Без привязки');
    expect(personBindingText(person({ final: final({ unresolved: true }) }))).toBe('Нужно решение');
  });
});

describe('filterPeople', () => {
  const rows = [
    person({ employee_id: 'a', status: 'by_hours', final: final({ key: 'K1', source: 'auto' }) }),
    person({ employee_id: 'b', status: 'by_name', final: final({ key: 'K2', source: 'auto' }) }),
    person({ employee_id: 'c', status: 'not_found', final: final({ unresolved: true }) }),
    person({ employee_id: 'd', status: 'not_found', final: final({ source: 'decision' }) }),
    person({ employee_id: 'e', status: 'search_failed', final: final({ unresolved: true }) }),
  ];
  const ids = (list: PersonRow[]) => list.map((r) => r.employee_id);
  it('по признакам', () => {
    expect(ids(filterPeople(rows, 'attention'))).toEqual(['c', 'e']);
    expect(ids(filterPeople(rows, 'by_hours'))).toEqual(['a']);
    expect(ids(filterPeople(rows, 'by_name'))).toEqual(['b']);
    expect(ids(filterPeople(rows, 'unbound'))).toEqual(['d']);
    expect(filterPeople(rows, 'all')).toHaveLength(5);
  });
});

describe('hoursLeaving', () => {
  const rows = [
    person({ employee_id: 'bound', hours_at_risk: 5, final: final({ key: 'K1', source: 'auto' }) }),
    person({ employee_id: 'unbound', hours_at_risk: 2.5, final: final({ source: 'decision' }) }),
    person({ employee_id: 'open', hours_at_risk: 4, final: final({ unresolved: true }) }),
    person({ employee_id: 'old-report', final: final({ source: 'decision' }) }),
  ];
  it('только у тех, кто без привязки или ждёт решения', () => {
    expect(rows.map(hoursLeaving)).toEqual([0, 2.5, 4, 0]);
    expect(totalHoursLeaving(rows)).toBe(6.5);
  });
});

describe('formatDiff', () => {
  it('знак, дробь и пустые месяцы', () => {
    expect(formatDiff(hours({ diff_pct: 2.5 }))).toBe('+2,5 %');
    expect(formatDiff(hours({ diff_pct: -1 }))).toBe('−1 %');
    expect(formatDiff(hours({ diff_pct: 0 }))).toBe('0 %');
    expect(formatDiff(hours({ db_hours: 0, dc_hours: 0 }))).toBe('—');
  });
});

describe('candidateLabel', () => {
  it('ФИО и логин', () => {
    expect(candidateLabel({ display_name: 'Петров Пётр', name: 'Petrov_P' })).toBe('Петров Пётр (Petrov_P)');
    expect(candidateLabel({ display_name: 'Петров Пётр', name: null })).toBe('Петров Пётр');
  });
});

describe('подписи', () => {
  it('есть для сбоя поиска и прерванной синхронизации', () => {
    expect(PERSON_STATUS_LABEL.search_failed).toBe('Поиск не удался');
    expect(SYNC_STATUS_LABEL.interrupted).toBeTruthy();
  });
});

describe('pollInterval', () => {
  const state = (job: { state: string; kind: string | null }, run: string | null) => ({
    job, sync_run: run ? { status: run } : null,
  });
  it('быстро при прогоне и применении, редко при полной синхронизации, выкл. в покое', () => {
    expect(pollInterval(undefined)).toBe(false);
    expect(pollInterval(state({ state: 'running', kind: 'dry_run' }, null))).toBe(2000);
    expect(pollInterval(state({ state: 'running', kind: 'apply' }, null))).toBe(2000);
    expect(pollInterval(state({ state: 'running', kind: 'full_sync' }, 'running'))).toBe(15000);
    expect(pollInterval(state({ state: 'idle', kind: null }, 'running'))).toBe(15000);
    expect(pollInterval(state({ state: 'done', kind: 'full_sync' }, 'ok'))).toBe(false);
    expect(pollInterval(state({ state: 'idle', kind: null }, 'interrupted'))).toBe(false);
  });
});

describe('applySummaryItems', () => {
  it('известные строки по порядку, ссылки на людей — сумма с разбивкой без нулей', () => {
    const items = applySummaryItems({
      issues_deleted: 3,
      settings: 12,
      people_refs: { issues_assignee: 5, issues_reporter: 0, kpi_approvals: 2, something_new: 4 },
      unknown_key: 7,
    });
    expect(items.map((i) => i.key)).toEqual(['settings', 'issues_deleted', 'people_refs']);
    const refs = items[2];
    expect(refs.value).toBe(11);
    expect(refs.detail).toBe('исполнители задач — 5, утверждённые KPI — 2');
    expect(items[0]).toEqual({ key: 'settings', label: 'Настроек полей переписано', value: 12, detail: null });
  });
  it('старый итог с числом вместо разбивки', () => {
    expect(applySummaryItems({ people_refs: 4 })).toEqual([
      { key: 'people_refs', label: 'Ссылок на людей переписано', value: 4, detail: null },
    ]);
  });
});

describe('counterLines', () => {
  it('без подписи не показывается', () => {
    expect(counterLines({ issues_read: 12, settings: 3 })).toEqual(['Прочитано задач: 12']);
    expect(counterLines({})).toEqual([]);
  });
});

describe('offerFullSyncRestart', () => {
  const idle = { state: 'idle' };
  it('не идёт и не завершилась успешно', () => {
    expect(offerFullSyncRestart(idle, null)).toBe(true);
    expect(offerFullSyncRestart(idle, { status: 'interrupted' })).toBe(true);
    expect(offerFullSyncRestart(idle, { status: 'failed' })).toBe(true);
    expect(offerFullSyncRestart(idle, { status: 'ok' })).toBe(false);
    expect(offerFullSyncRestart(idle, { status: 'running' })).toBe(false);
    expect(offerFullSyncRestart({ state: 'running' }, { status: 'failed' })).toBe(false);
  });
});

describe('dcUserLabel', () => {
  it('почта и пометка неактивного', () => {
    expect(dcUserLabel({ display_name: 'Петров Пётр', name: 'Petrov_P', email: 'p@x.ru', active: false }))
      .toBe('Петров Пётр (Petrov_P), p@x.ru — неактивен');
    expect(dcUserLabel({ display_name: 'Петров Пётр', name: null, active: true })).toBe('Петров Пётр');
  });
});

describe('matchedWorklogsLabel', () => {
  it('согласование числа', () => {
    expect(matchedWorklogsLabel(1)).toBe('1 совпавшее списание');
    expect(matchedWorklogsLabel(3)).toBe('3 совпавших списания');
    expect(matchedWorklogsLabel(12)).toBe('12 совпавших списаний');
    expect(matchedWorklogsLabel(21)).toBe('21 совпавшее списание');
    expect(matchedWorklogsLabel(111)).toBe('111 совпавших списаний');
  });
});
