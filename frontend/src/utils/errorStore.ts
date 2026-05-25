/** Хранилище ошибок и контекста для feedback-формы. */

export interface NetworkErrorEntry {
  ts: string;
  method: string;
  url: string;
  status: number | null;
  detail: string;
  requestBody?: string;
}

export interface ConsoleErrorEntry {
  ts: string;
  message: string;
  stack?: string;
  source?: string;
}

export interface FeedbackContext {
  user_agent: string;
  language: string;
  screen_w: number;
  screen_h: number;
  timezone: string;
  active_team: string | null;
  active_period: string | null;
  theme: string | null;
  console_errors: ConsoleErrorEntry[];
  network_errors: NetworkErrorEntry[];
}

const MAX_NETWORK = 20;
const MAX_CONSOLE = 20;

const networkErrors: NetworkErrorEntry[] = [];
const consoleErrors: ConsoleErrorEntry[] = [];
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((fn) => fn());
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export function pushError(entry: NetworkErrorEntry): void {
  networkErrors.push(entry);
  if (networkErrors.length > MAX_NETWORK) networkErrors.shift();
  notify();
}

export function pushConsoleError(entry: ConsoleErrorEntry): void {
  consoleErrors.push(entry);
  if (consoleErrors.length > MAX_CONSOLE) consoleErrors.shift();
  notify();
}

export function getNetworkErrors(): readonly NetworkErrorEntry[] {
  return networkErrors;
}

export function getConsoleErrors(): readonly ConsoleErrorEntry[] {
  return consoleErrors;
}

export function getErrorCount(): number {
  return networkErrors.length + consoleErrors.length;
}

export function clearErrors(): void {
  networkErrors.length = 0;
  consoleErrors.length = 0;
  notify();
}

/** Builds a snapshot context for a bug report. */
export function buildContext(): FeedbackContext {
  let activeTeam: string | null = null;
  let activePeriod: string | null = null;
  let theme: string | null = null;
  try {
    const params = new URLSearchParams(window.location.search);
    activeTeam = params.get('team') || params.get('teams');
    const y = params.get('year');
    const q = params.get('quarter');
    if (y && q) activePeriod = `${y}Q${q}`;
    theme = document.documentElement.getAttribute('data-theme');
  } catch {
    // ignore
  }
  return {
    user_agent: navigator.userAgent,
    language: navigator.language,
    screen_w: window.screen.width,
    screen_h: window.screen.height,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    active_team: activeTeam,
    active_period: activePeriod,
    theme,
    console_errors: [...consoleErrors],
    network_errors: [...networkErrors],
  };
}

