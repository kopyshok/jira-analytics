import { describe, expect, it } from 'vitest';
import { normalizePath } from '../normalizePath';

describe('normalizePath', () => {
  it('returns known path unchanged', () => {
    expect(normalizePath('/dashboard')).toBe('/dashboard');
  });

  it('replaces project key segment', () => {
    expect(normalizePath('/projects/PROJ-123')).toBe('/projects/:key');
  });

  it('replaces uuid id segment in scenarios', () => {
    expect(normalizePath('/scenarios/abc-def-uuid/edit')).toBe('/scenarios/:id/edit');
  });

  it('strips query string', () => {
    expect(normalizePath('/dashboard?team=foo')).toBe('/dashboard');
  });

  it('returns null for unknown path', () => {
    expect(normalizePath('/nonsense/route')).toBeNull();
  });
});
