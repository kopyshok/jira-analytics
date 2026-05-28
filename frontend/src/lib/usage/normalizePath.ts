import { KNOWN_ROUTES } from './routeTable';

const ROUTE_PATTERNS: { regex: RegExp; route: string }[] = KNOWN_ROUTES.map((route) => {
  const pattern = route
    .replace(/:[a-z]+/gi, '([^/]+)')
    .replace(/\//g, '\\/');
  return { regex: new RegExp(`^${pattern}$`), route };
});

export function normalizePath(rawPath: string): string | null {
  const path = rawPath.split('?')[0].replace(/\/+$/, '') || '/';
  for (const { regex, route } of ROUTE_PATTERNS) {
    if (regex.test(path)) return route;
  }
  return null;
}
