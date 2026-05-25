/** Перехватывает console.error / window.onerror / unhandledrejection в ring-buffer. */
import { pushConsoleError } from './errorStore';

let installed = false;

export function installConsoleCapture(): void {
  if (installed) return;
  installed = true;

  const originalError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    try {
      const msg = args
        .map((a) =>
          a instanceof Error ? a.message : typeof a === 'string' ? a : JSON.stringify(a),
        )
        .join(' ');
      const errArg = args.find((a): a is Error => a instanceof Error);
      pushConsoleError({
        ts: new Date().toISOString(),
        message: msg,
        stack: errArg?.stack,
      });
    } catch {
      // never let logging crash the app
    }
    originalError(...args);
  };

  window.addEventListener('error', (ev) => {
    pushConsoleError({
      ts: new Date().toISOString(),
      message: ev.message,
      stack: ev.error instanceof Error ? ev.error.stack : undefined,
      source: ev.filename ? `${ev.filename}:${ev.lineno}` : undefined,
    });
  });

  window.addEventListener('unhandledrejection', (ev) => {
    const reason: unknown = ev.reason;
    pushConsoleError({
      ts: new Date().toISOString(),
      message: reason instanceof Error ? reason.message : String(reason),
      stack: reason instanceof Error ? reason.stack : undefined,
      source: 'unhandledrejection',
    });
  });
}
