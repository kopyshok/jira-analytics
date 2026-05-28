import { describe, expect, it } from 'vitest';
import { normalizePath } from '../normalizePath';

describe('normalizePath', () => {
  it('returns root unchanged', () => {
    expect(normalizePath('/')).toBe('/');
  });

  it('returns known path unchanged', () => {
    expect(normalizePath('/analytics')).toBe('/analytics');
  });

  it('matches nested known path', () => {
    expect(normalizePath('/analytics/work-type-report')).toBe('/analytics/work-type-report');
  });

  it('replaces project key segment', () => {
    expect(normalizePath('/projects/PROJ-123')).toBe('/projects/:key');
  });

  it('strips query string', () => {
    expect(normalizePath('/sync?team=foo')).toBe('/sync');
  });

  it('returns null for unknown path', () => {
    expect(normalizePath('/nonsense/route')).toBeNull();
  });
});
