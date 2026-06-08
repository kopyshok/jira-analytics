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

  it('aurora-light is the inverted variant', () => {
    expect(APP_THEMES['aurora-light'].tokens.pageBg).toBe('#eef2fb');
    expect(APP_THEMES['aurora-light'].tokens.primary).toBe('#0ea5e9');
  });

  it('AppTheme union includes both Aurora values', () => {
    const themes: AppTheme[] = ['dark', 'dark-blue', 'dark-slate', 'dark-charcoal', 'aurora-dark', 'aurora-light'];
    expect(themes).toHaveLength(6);
  });
});
