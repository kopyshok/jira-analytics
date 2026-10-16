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

  it('warm-light — скин «Тёплая» поверх Aurora light', () => {
    expect(APP_THEMES['warm-light'].label).toBe('Тёплая');
    expect(APP_THEMES['warm-light'].mode).toBe('light');
    expect(APP_THEMES['warm-light'].skin).toBe('warm');
    expect(APP_THEMES['warm-light'].tokens.pageBg).toBe('#EFEBE5');
    expect(APP_THEMES['warm-light'].tokens.primary).toBe('#2F6B5A');
    // У самих тем Aurora скина нет.
    expect(APP_THEMES['aurora-dark'].skin).toBeUndefined();
    expect(APP_THEMES['aurora-light'].skin).toBeUndefined();
  });

  it('AppTheme union — две темы Aurora и скин «Тёплая»', () => {
    const themes: AppTheme[] = ['aurora-dark', 'aurora-light', 'warm-light'];
    expect(themes).toHaveLength(3);
    expect(Object.keys(APP_THEMES)).toEqual(['aurora-dark', 'aurora-light', 'warm-light']);
    // Колонка темы в БД — String(20).
    for (const id of Object.keys(APP_THEMES)) expect(id.length).toBeLessThanOrEqual(20);
  });
});
