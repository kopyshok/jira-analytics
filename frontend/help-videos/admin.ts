// Демо-администратор для роликов по настройкам: создаётся в копии базы (prepare-db.ts),
// входит в global-setup.ts. В ролике: test.use({ storageState: ADMIN_STATE }).
import { fileURLToPath } from 'node:url';

export const ADMIN_EMAIL = 'admin@example.com';
const port = Number(process.env.VIDEOS_BACKEND_PORT ?? 8012); // как в playwright.videos.config.ts
export const ADMIN_STATE = fileURLToPath(new URL(`../../data/demo_run_${port}.admin.json`, import.meta.url));
