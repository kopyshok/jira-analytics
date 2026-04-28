import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const currentDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(currentDir, '..', '..');
const dataDir = resolve(repoRoot, 'data');
const dbPath = resolve(dataDir, 'e2e.db');

function runPythonModule(args: string[]) {
  const candidates =
    process.platform === 'win32'
      ? [
          { command: 'py', args: ['-3.10', ...args] },
          { command: 'python', args },
        ]
      : [
          { command: 'python3', args },
          { command: 'python', args },
        ];

  for (const candidate of candidates) {
    try {
      execFileSync(candidate.command, candidate.args, {
        cwd: repoRoot,
        stdio: 'inherit',
        env: {
          ...process.env,
          DATABASE_URL: 'sqlite:///./data/e2e.db',
          DEBUG: 'false',
        },
      });
      return;
    } catch (error) {
      const nodeError = error as NodeJS.ErrnoException;
      if (nodeError.code !== 'ENOENT') {
        throw error;
      }
    }
  }

  throw new Error('Python executable was not found for E2E database setup.');
}

export default async function globalSetup() {
  mkdirSync(dataDir, { recursive: true });

  // On Windows the webServer plugin (a Playwright plugin) starts BEFORE
  // globalSetup runs.  The backend process opens e2e.db immediately, so
  // rmSync fails with EPERM — Windows won't unlink an open file.
  // On Linux/CI the file can be unlinked while open (POSIX semantics).
  //
  // Windows strategy: try to delete; if EPERM, the backend is already
  // running with a valid DB — just run alembic + seed idempotently and
  // continue.  The backend sees the seeded data because SQLite WAL allows
  // concurrent access.
  let freshDb = true;
  try {
    rmSync(dbPath, { force: true });
    rmSync(`${dbPath}-shm`, { force: true });
    rmSync(`${dbPath}-wal`, { force: true });
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    if (code === 'EPERM' || code === 'EBUSY') {
      // Backend is running and has the file open.  Run setup idempotently.
      freshDb = false;
    } else {
      throw err;
    }
  }

  if (freshDb) {
    // Normal path: fresh DB — run full migration + seed.
    runPythonModule(['-m', 'alembic', 'upgrade', 'head']);
    runPythonModule(['scripts/seed_e2e.py']);
    return;
  }

  // Windows fallback: DB file is locked by the backend.  Run alembic
  // (idempotent no-op on an already-migrated DB) and the seed script
  // (guards with "if not exists") so the test user and fixtures are present.
  runPythonModule(['-m', 'alembic', 'upgrade', 'head']);
  runPythonModule(['scripts/seed_e2e.py']);

  runPythonModule(['-m', 'alembic', 'upgrade', 'head']);
  runPythonModule(['scripts/seed_e2e.py']);
}
