import { describe, expect, it } from 'vitest';
import { blockAudience, notAppliedText } from './scheduledBlocks';

describe('blockAudience', () => {
  it('вся команда, если нет ни ролей, ни сотрудников', () => {
    expect(blockAudience({ role_labels: [], employee_names: [] })).toBe('вся команда');
  });
  it('роли, затем сотрудники', () => {
    expect(blockAudience({ role_labels: ['Аналитик', 'РП'], employee_names: ['Иванов'] }))
      .toBe('Аналитик, РП · Иванов');
  });
});

describe('notAppliedText', () => {
  it('пусто, если период действует на всех', () => {
    expect(notAppliedText({ not_applied: [] })).toBe('');
    expect(notAppliedText({})).toBe('');
  });
  it('группирует людей по месяцам', () => {
    expect(notAppliedText({
      not_applied: [
        { employee_name: 'Копышков', month: '2026-11-01' },
        { employee_name: 'Фокеева', month: '2026-10-01' },
        { employee_name: 'Копышков', month: '2026-10-01' },
      ],
    })).toBe('Не действует в октябре — Фокеева, Копышков; в ноябре — Копышков: '
      + 'у них свой период того же вида по роли или лично.');
  });
  it('склоняет май и март', () => {
    expect(notAppliedText({ not_applied: [{ employee_name: 'А', month: '2026-05-01' }] }))
      .toContain('в мае');
    expect(notAppliedText({ not_applied: [{ employee_name: 'А', month: '2026-03-01' }] }))
      .toContain('в марте');
  });
});
