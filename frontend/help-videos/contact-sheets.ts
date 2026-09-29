// Сетки кадров для просмотра роликов глазами: `npm run videos:sheets [-- <ролик> ...]`.
// Кадр каждые 2 с, лист 3×4 = 24 с ролика → data/frames/<ролик>-sheet-1.png, -2.png, …
// Ролик 90 с — 4 листа. Кадр шириной 520: подписи читаются. Нужен ffmpeg в PATH.
import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';

const videosDir = resolve(import.meta.dirname, '..', 'public', 'help-videos');
const framesDir = resolve(import.meta.dirname, '..', '..', 'data', 'frames');
mkdirSync(framesDir, { recursive: true });

const ids = process.argv.slice(2).length
  ? process.argv.slice(2)
  : readdirSync(videosDir).filter((f) => f.endsWith('.webm')).map((f) => f.replace(/\.webm$/, ''));

for (const id of ids) {
  // Старые листы ролика убираем: новый может оказаться короче.
  for (const f of readdirSync(framesDir)) if (f.startsWith(`${id}-sheet`)) rmSync(resolve(framesDir, f));
  execFileSync('ffmpeg', [
    '-y', '-loglevel', 'error', '-i', resolve(videosDir, `${id}.webm`),
    '-vf', 'fps=1/2,scale=520:-1,tile=3x4:padding=4:color=white',
    resolve(framesDir, `${id}-sheet-%d.png`),
  ]);
  console.log(readdirSync(framesDir).filter((f) => f.startsWith(`${id}-sheet-`)).map((f) => resolve(framesDir, f)).join('\n'));
}
