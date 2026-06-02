import { pushError } from '../utils/errorStore';

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
export const BASE_URL = configuredBaseUrl.replace(/\/$/, '');

/** Эмитится при HTTP 401 от любого API-вызова. AuthProvider слушает и чистит сессию. */
export const AUTH_EXPIRED_EVENT = 'auth:expired';

export const boolParam = (v?: boolean): string | undefined =>
  v === undefined ? undefined : v ? 'true' : 'false';

// Недавно удалённые URL'ы — для подавления ложноположительных 404, которые
// летят от still-mounted TanStack-observers после DELETE того же ресурса
// (race между re-render'ом компонента и onMutate'ом мутации).
const recentlyDeleted = new Map<string, number>();
const DELETE_SUPPRESS_WINDOW_MS = 2000;

function markDeleted(baseUrl: string): void {
  const now = Date.now();
  recentlyDeleted.set(baseUrl, now);
  // Чистим старые записи, чтобы map не рос.
  for (const [k, ts] of recentlyDeleted) {
    if (now - ts > DELETE_SUPPRESS_WINDOW_MS) recentlyDeleted.delete(k);
  }
}

/** FastAPI 422 detail — массив `{loc, msg, type}`; HTTPException — строка. Делаем читаемо. */
function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((d) => {
      if (typeof d === 'string') return d;
      if (d && typeof d === 'object') {
        const o = d as { loc?: unknown[]; msg?: string };
        const loc = Array.isArray(o.loc) ? o.loc.slice(1).join('.') : '';
        return loc ? `${loc}: ${o.msg ?? ''}`.trim() : (o.msg ?? JSON.stringify(d));
      }
      return String(d);
    }).join('; ');
  }
  if (detail && typeof detail === 'object') {
    const o = detail as { msg?: string; message?: string };
    return o.msg ?? o.message ?? JSON.stringify(detail);
  }
  return '';
}


function isSuppressed404(method: string, status: number | null, url: string): boolean {
  if (method !== 'GET' || status !== 404) return false;
  const now = Date.now();
  // Совпадение по префиксу: DELETE /backlog/{id} глушит GET /backlog/{id}
  // и GET /backlog/{id}/allocations в пределах окна.
  for (const [base, ts] of recentlyDeleted) {
    if (now - ts > DELETE_SUPPRESS_WINDOW_MS) continue;
    if (url === base || url.startsWith(`${base}/`) || url.startsWith(`${base}?`)) {
      return true;
    }
  }
  return false;
}

function buildApiUrl(path: string): URL {
  const browserOrigin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
  return new URL(`${BASE_URL}${path}`, browserOrigin);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, string | undefined>,
  signal?: AbortSignal,
): Promise<T> {
  const url = buildApiUrl(path);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') url.searchParams.set(k, v);
    });
  }

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method,
      headers: {
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal,
      credentials: 'include',
    });
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e;
    pushError({
      ts: new Date().toISOString(), method, url: url.toString(),
      status: null, detail: (e as Error).message,
      requestBody: body ? JSON.stringify(body) : undefined,
    });
    throw e;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = formatDetail(err.detail) || res.statusText;
    // 401 = истёк/невалидный cookie. Сообщаем AuthProvider — он сбросит user
    // и ProtectedRoute перенаправит на /login. В errorStore не льём.
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
    } else if (!isSuppressed404(method, res.status, url.toString())) {
      pushError({
        ts: new Date().toISOString(), method, url: url.toString(),
        status: res.status, detail,
        requestBody: body ? JSON.stringify(body) : undefined,
      });
    }
    throw new Error(detail);
  }
  if (method === 'DELETE') markDeleted(url.toString());
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  const contentType = res.headers.get('content-type') ?? '';
  if (!contentType.includes('application/json')) return undefined as T;
  return JSON.parse(text) as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | undefined>, signal?: AbortSignal) =>
    request<T>('GET', path, undefined, params, signal),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('POST', path, body, undefined, signal),
  put: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('PUT', path, body, undefined, signal),
  patch: <T>(path: string, body?: unknown, signal?: AbortSignal) =>
    request<T>('PATCH', path, body, undefined, signal),
  del: <T>(path: string, signal?: AbortSignal) =>
    request<T>('DELETE', path, undefined, undefined, signal),
  download: async (path: string, params?: Record<string, string | undefined>) => {
    const url = buildApiUrl(path);
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== '') url.searchParams.set(k, v);
      });
    }
    const res = await fetch(url.toString(), { credentials: 'include' });
    if (!res.ok) throw new Error(`Download failed: ${res.statusText}`);
    const blob = await res.blob();
    const filename = path.split('/').pop() || 'download';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  },
};
