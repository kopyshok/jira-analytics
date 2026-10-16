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

  it('AppTheme union — две темы Aurora и обложка «Швейцарская»', () => {
    const themes: AppTheme[] = ['aurora-dark', 'aurora-light', 'swiss-light'];
    expect(themes).toHaveLength(3);
    expect(Object.keys(APP_THEMES)).toEqual(['aurora-dark', 'aurora-light', 'swiss-light']);
  });

  it('у Aurora-тем нет обложки, «Швейцарская» — обложка над светлой', () => {
    expect(APP_THEMES['aurora-dark'].skin).toBeUndefined();
    expect(APP_THEMES['aurora-light'].skin).toBeUndefined();
    expect(APP_THEMES['aurora-dark'].mode).toBe('dark');
    expect(APP_THEMES['aurora-light'].mode).toBe('light');
    expect(APP_THEMES['swiss-light']).toMatchObject({ label: 'Швейцарская', mode: 'light', skin: 'swiss' });
    expect(APP_THEMES['swiss-light'].tokens.pageBg).toBe('#FFFFFF');
    expect(APP_THEMES['swiss-light'].tokens.primary).toBe('#E5401F');
  });

  it('id тем помещаются в колонку БД (String(20))', () => {
    for (const id of Object.keys(APP_THEMES)) expect(id.length).toBeLessThanOrEqual(20);
  });
});
