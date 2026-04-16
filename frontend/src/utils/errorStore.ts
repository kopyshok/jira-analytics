/** Хранилище последних API-ошибок для баг-репорта. */

export interface ErrorEntry {
  ts: string;
  method: string;
  url: string;
  status: number | null;
  detail: string;
  requestBody?: string;
}

const MAX_ENTRIES = 30;
const entries: ErrorEntry[] = [];
const listeners = new Set<() => void>();

export function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

function notify() { listeners.forEach(fn => fn()); }

export function pushError(entry: ErrorEntry) {
  entries.push(entry);
  if (entries.length > MAX_ENTRIES) entries.shift();
  notify();
}

export function getErrors(): readonly ErrorEntry[] {
  return entries;
}

export function clearErrors() {
  entries.length = 0;
  notify();
}

export function getErrorCount() {
  return entries.length;
}

export function buildBugReport(): string {
  const lines: string[] = [
    '# Bug Report',
    '',
    `**URL:** ${window.location.href}`,
    `**Time:** ${new Date().toISOString()}`,
    `**UA:** ${navigator.userAgent}`,
    '',
  ];

  if (entries.length === 0) {
    lines.push('No API errors recorded.');
  } else {
    lines.push(`## API Errors (${entries.length})`);
    lines.push('');
    for (const e of entries) {
      lines.push(`### ${e.method} ${e.url}`);
      lines.push(`- **Time:** ${e.ts}`);
      lines.push(`- **Status:** ${e.status ?? 'network error'}`);
      lines.push(`- **Detail:** ${e.detail}`);
      if (e.requestBody) {
        lines.push(`- **Body:** \`${e.requestBody.slice(0, 500)}\``);
      }
      lines.push('');
    }
  }

  return lines.join('\n');
}
