import { describe, it, expect } from 'vitest';
import { APP_THEMES, type AppTheme } from '../constants';

describe('APP_THEMES Aurora', () => {
  it('includes aurora-dark and aurora-light', () => {
    expect(APP_THEMES['aurora-dark']).toBeDefined();
    expect(APP_THEMES['aurora-light']).toBeDefined();
  });

  it('aurora-dark uses cyan→violet accents', () => {
    expect(APP_THEMES['aurora-dark'].tokens.primary).toBe('#38bdf8');
    expect(APP_THEMES['aurora-dark'].tokens.primarySecondary).toBe('#a78bfa');
  });

  it('aurora-light is the porcelain (neumorphic) variant', () => {
    expect(APP_THEMES['aurora-light'].tokens.pageBg).toBe('#e6ebf2');
    expect(APP_THEMES['aurora-light'].tokens.primary).toBe('#3b6ef5');
  });

  it('AppTheme union — dark-blue + 2 Aurora', () => {
    const themes: AppTheme[] = ['dark-blue', 'aurora-dark', 'aurora-light'];
    expect(themes).toHaveLength(3);
    expect(Object.keys(APP_THEMES)).toHaveLength(3);
  });

  it('Aurora темы помечены isNew', () => {
    expect(APP_THEMES['aurora-dark'].isNew).toBe(true);
    expect(APP_THEMES['aurora-light'].isNew).toBe(true);
    expect(APP_THEMES['dark-blue'].isNew).toBeUndefined();
  });
});
