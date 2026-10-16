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

  it('AppTheme union — две темы Aurora и скин «Цветовые зоны»', () => {
    const themes: AppTheme[] = ['aurora-dark', 'aurora-light', 'zones-light'];
    expect(themes).toHaveLength(3);
    expect(Object.keys(APP_THEMES)).toEqual(['aurora-dark', 'aurora-light', 'zones-light']);
  });

  it('zones-light — скин поверх Aurora light с кобальтовым акцентом', () => {
    expect(APP_THEMES['zones-light'].mode).toBe('light');
    expect(APP_THEMES['zones-light'].skin).toBe('zones');
    expect(APP_THEMES['zones-light'].tokens.primary).toBe('#2546A6');
    expect(APP_THEMES['aurora-light'].skin).toBeUndefined();
    expect(APP_THEMES['aurora-dark'].skin).toBeUndefined();
  });
});
