import { pushError } from '../utils/errorStore';

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
const BASE_URL = configuredBaseUrl.replace(/\/$/, '');

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, string | undefined>): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '') url.searchParams.set(k, v);
    });
  }

  let res: Response;
  try {
    res = await fetch(url.toString(), {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (e) {
    pushError({
      ts: new Date().toISOString(), method, url: url.toString(),
      status: null, detail: (e as Error).message,
      requestBody: body ? JSON.stringify(body) : undefined,
    });
    throw e;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail || res.statusText;
    pushError({
      ts: new Date().toISOString(), method, url: url.toString(),
      status: res.status, detail,
      requestBody: body ? JSON.stringify(body) : undefined,
    });
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  get: <T>(path: string, params?: Record<string, string | undefined>) => request<T>('GET', path, undefined, params),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
  download: async (path: string, params?: Record<string, string | undefined>) => {
    const url = new URL(`${BASE_URL}${path}`);
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        if (v !== undefined && v !== '') url.searchParams.set(k, v);
      });
    }
    const res = await fetch(url.toString());
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
