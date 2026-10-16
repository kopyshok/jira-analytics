import { describe, expect, it } from 'vitest';
import { planStatusTag } from '../rpPlanStatus';

describe('planStatusTag', () => {
  it.each([
    ['ready', 'Готово', 'cyan'],
    ['stale', 'Требуется пересчёт', 'orange'],
    ['computing', 'Считается…', 'blue'],
    ['draft', 'Черновик', 'default'],
    ['что-то новое', 'Черновик', 'default'],
  ])('%s → %s', (status, label, color) => {
    expect(planStatusTag(status)).toEqual({ label, color });
  });
});
