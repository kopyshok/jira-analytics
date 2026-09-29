// Свежая копия демо-базы перед съёмкой: data/demo.db → data/<VIDEOS_RUN_DB>.
// Запускается из команды бэкенда в playwright.videos.config.ts, ДО uvicorn:
// сервер Playwright стартует раньше globalSetup, поэтому копировать там поздно.
import { copyFileSync, existsSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';

const dataDir = resolve(import.meta.dirname, '..', '..', 'data');
const source = resolve(dataDir, 'demo.db');
const target = resolve(dataDir, process.env.VIDEOS_RUN_DB ?? 'demo_run.db');

if (!existsSync(source)) {
  console.error(
    `Нет демо-базы ${source}. Сначала соберите её: ` +
      'py -3.10 scripts/demo_db/build_demo_db.py --source <база> --out data/demo.db',
  );
  process.exit(1);
}

// Рядом с демо-базой лежит журнал — её кто-то открывал на запись или сборка оборвалась.
// Копия одного файла без журнала может оказаться неполной: лучше пересобрать базу.
const journals = ['-wal', '-journal'].map((suffix) => `${source}${suffix}`).filter((path) => existsSync(path));
if (journals.length) {
  console.error(
    `Рядом с демо-базой есть журнал (${journals.join(', ')}). Пересоберите её: ` +
      'py -3.10 scripts/demo_db/build_demo_db.py --source <база> --out data/demo.db --force',
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
// Утверждение квартала KPI включено: ролик kpi-review показывает кнопку «Утвердить квартал».
db.exec("DELETE FROM app_settings WHERE key = 'kpi_approval_enabled'");
db.exec(
  "INSERT INTO app_settings (id, key, value, created_at, updated_at) " +
    "VALUES (lower(hex(randomblob(16))), 'kpi_approval_enabled', 'true', datetime('now'), datetime('now'))",
);
db.close();

console.log(`help-videos: ${target} готова`);
