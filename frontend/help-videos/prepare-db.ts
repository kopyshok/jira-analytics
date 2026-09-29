// Свежая копия демо-базы перед съёмкой: data/demo.db → data/demo_run.db.
// Запускается из команды бэкенда в playwright.videos.config.ts, ДО uvicorn:
// сервер Playwright стартует раньше globalSetup, поэтому копировать там поздно.
import { copyFileSync, existsSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

const dataDir = resolve(import.meta.dirname, '..', '..', 'data');
const source = resolve(dataDir, 'demo.db');
const target = resolve(dataDir, 'demo_run.db');

if (!existsSync(source)) {
  console.error(
    `Нет демо-базы ${source}. Сначала соберите её: ` +
      'py -3.10 scripts/demo_db/build_demo_db.py --source <база> --out data/demo.db',
  );
  process.exit(1);
}

for (const suffix of ['', '-wal', '-shm', '-journal']) {
  rmSync(`${target}${suffix}`, { force: true });
}
copyFileSync(source, target);

// Расписания синхронизации в копии выключены: съёмка не должна ходить в Jira.
const db = new DatabaseSync(target);
db.exec('UPDATE sync_schedule SET enabled = 0');
db.close();

console.log(`help-videos: ${target} готова`);
