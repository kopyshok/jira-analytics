import { describe, expect, it } from 'vitest';
import { rowLeftBorder } from './backlogRowStripe';

describe('rowLeftBorder', () => {
  it('у строки есть состояние — полосу рисует класс состояния, встроенной нет', () => {
    expect(rowLeftBorder(true, 'row-state-deficit')).toBeUndefined();
    expect(rowLeftBorder(false, 'row-state-no-estimates')).toBeUndefined();
    expect(rowLeftBorder(true, 'row-state-in-work')).toBeUndefined();
  });
  it('без состояния: включено — полоса акцента, не включено — прозрачная', () => {
    expect(rowLeftBorder(true, '')).toBe('3px solid var(--accent-1, #00c9c8)');
    expect(rowLeftBorder(false, '')).toBe('3px solid transparent');
  });
});
