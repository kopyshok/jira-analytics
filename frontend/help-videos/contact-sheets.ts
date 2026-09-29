// Сетка кадров для просмотра роликов одним взглядом: `npm run videos:sheets [-- <ролик> ...]`.
// Кадр каждые 2 с, 4 в ряд → data/frames/<ролик>-sheet.png. Нужен ffmpeg в PATH.
import { execFileSync } from 'node:child_process';
import { mkdirSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const videosDir = resolve(import.meta.dirname, '..', 'public', 'help-videos');
const framesDir = resolve(import.meta.dirname, '..', '..', 'data', 'frames');
mkdirSync(framesDir, { recursive: true });

const ids = process.argv.slice(2).length
  ? process.argv.slice(2)
  : readdirSync(videosDir).filter((f) => f.endsWith('.webm')).map((f) => f.replace(/\.webm$/, ''));

for (const id of ids) {
  const out = resolve(framesDir, `${id}-sheet.png`);
  // ponytail: 4×6 = до 48 с ролика; длиннее — хвост в сетку не попадёт
  execFileSync('ffmpeg', [
    '-y', '-loglevel', 'error', '-i', resolve(videosDir, `${id}.webm`),
    '-vf', 'fps=1/2,scale=480:-1,tile=4x6:padding=4:color=white', '-frames:v', '1', out,
  ]);
  console.log(out);
}
