import { describe, expect, it } from 'vitest';
import { resolveLayout, treeLevels } from './useAnalyticsLayout';

describe('treeLevels', () => {
  it('порядок из настройки отчёта; одна команда — без уровня «Команда»; задача в конце', () => {
    const { visibleLevels } = resolveLayout({
      group_order: ['team', 'role', 'work_type', 'employee', 'subgroup', 'category', 'issue'],
      hidden_levels: ['subgroup', 'category'],
    });
    expect(treeLevels(visibleLevels, 'all')).toEqual(['team', 'role', 'work_type', 'employee', 'issue']);
    expect(treeLevels(visibleLevels, 'Команда 1С')).toEqual(['role', 'work_type', 'employee', 'issue']);
  });
});
