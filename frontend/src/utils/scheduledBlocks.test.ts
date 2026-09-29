import { describe, expect, it } from 'vitest';
import { blockAudience } from './scheduledBlocks';

describe('blockAudience', () => {
  it('вся команда, если нет ни ролей, ни сотрудников', () => {
    expect(blockAudience({ role_labels: [], employee_names: [] })).toBe('вся команда');
  });
  it('роли, затем сотрудники', () => {
    expect(blockAudience({ role_labels: ['Аналитик', 'РП'], employee_names: ['Иванов'] }))
      .toBe('Аналитик, РП · Иванов');
  });
});
