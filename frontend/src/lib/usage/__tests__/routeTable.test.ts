import { describe, expect, it } from 'vitest';
import routesSrc from '../../../routes.tsx?raw';
import { KNOWN_ROUTES } from '../routeTable';
import { PATH_LABELS } from '../../../components/admin/usage/pathLabels';

// ponytail: regex по исходнику routes.tsx вместо импорта роутера — импорт тянет все страницы.
// Ломается, если роуты переедут из routes.tsx в другой файл.
function routerPaths(): string[] {
  const paths = [...routesSrc.matchAll(/path:\s*'([^']+)'/g)].map((m) => m[1]);
  return paths
    .filter((p) => !p.includes('Navigate'))
    .map((p) => (p.startsWith('/') ? p : `/${p}`));
}

describe('routeTable', () => {
  it('покрывает все роуты приложения', () => {
    // /scope — редирект, /desk/:token — публичный стол без авторизации
    const skip = new Set(['/scope', '/desk/:token']);
    const missing = routerPaths().filter((p) => !skip.has(p) && !KNOWN_ROUTES.includes(p));
    expect(missing).toEqual([]);
  });

  it('у каждого раздела есть человекочитаемое имя', () => {
    const missing = KNOWN_ROUTES.filter((p) => !PATH_LABELS[p]);
    expect(missing).toEqual([]);
  });
});
