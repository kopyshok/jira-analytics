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
  rmSync(dbPath, { force: true });
  rmSync(`${dbPath}-shm`, { force: true });
  rmSync(`${dbPath}-wal`, { force: true });

  runPythonModule(['-m', 'alembic', 'upgrade', 'head']);
}
