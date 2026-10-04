// Склейка глав сводного ролика: data/release-video/clips/*.webm по порядку имён →
// data/release-video/release-<версия>.mp4 и сетка кадров для просмотра.
// Главы, снятые с диктором (VOICE=1), лежат с фразами в <глава>.cues.json: их голос
// сдвигается на начало главы в общем ролике, музыка идёт через весь ролик.
// `node --no-warnings help-videos/release/assemble.ts`. Нужен ffmpeg в PATH.
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, rmSync } from 'node:fs';
import { resolve } from 'node:path';
import { type Cue, duration, mix } from '../voice.ts';
import { CLIPS_DIR, RELEASE } from './common.ts';

const outDir = resolve(CLIPS_DIR, '..');
const clips = readdirSync(CLIPS_DIR).filter((f) => f.endsWith('.webm')).sort();
if (!clips.length) throw new Error(`Нет глав в ${CLIPS_DIR}`);

// Запись Playwright — с плавающей частотой кадров: приводим к 25 к/с перед склейкой.
// Главы по приложению начинаются с полусекунды «Загрузка…» до заголовка — её срезаем;
// заставка и финал (00, 09) — свои страницы, их не трогаем.
const inputs = clips.flatMap((f) => ['-i', resolve(CLIPS_DIR, f)]);
const cut = (f: string) => (/^0[1-8]-/.test(f) ? 0.5 : 0);
const trim = (f: string) => (cut(f) ? `trim=start=${cut(f)},setpts=PTS-STARTPTS,` : '');
const norm = clips.map((f, i) => `[${i}:v]${trim(f)}fps=25,scale=1920:1080,setsar=1[v${i}]`).join(';');
const concat = `${clips.map((_, i) => `[v${i}]`).join('')}concat=n=${clips.length}:v=1:a=0[out]`;
const out = resolve(outDir, `release-${RELEASE}.mp4`);
const cuesOf = (f: string) => resolve(CLIPS_DIR, f.replace(/\.webm$/, '.cues.json'));
const voiced = clips.some((f) => existsSync(cuesOf(f)));
const silent = voiced ? resolve(outDir, `release-${RELEASE}.silent.mp4`) : out;
execFileSync('ffmpeg', [
  '-y', '-loglevel', 'error', ...inputs,
  '-filter_complex', `${norm};${concat}`, '-map', '[out]',
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '22', '-movflags', '+faststart', silent,
]);
if (voiced) {
  const cues: Cue[] = [];
  let startMs = 0;
  for (const f of clips) {
    if (existsSync(cuesOf(f))) {
      for (const c of JSON.parse(readFileSync(cuesOf(f), 'utf8')) as Cue[]) {
        cues.push({ file: c.file, at: Math.max(0, Math.round(startMs + c.at - cut(f) * 1000)) });
      }
    }
    startMs += (duration(resolve(CLIPS_DIR, f)) - cut(f)) * 1000;
  }
  mix(silent, cues, out);
  rmSync(silent);
}
console.log(`${clips.length} глав → ${out}`);

// Кадр каждые 5 с, 6 в ряд: строк столько, чтобы лист вместил весь ролик.
const sheet = resolve(outDir, `release-${RELEASE}-sheet.png`);
execFileSync('ffmpeg', [
  '-y', '-loglevel', 'error', '-i', out,
  '-vf', `fps=1/5,scale=480:-1,tile=6x${Math.ceil(duration(out) / 30)}:padding=4:color=white`, '-frames:v', '1', sheet,
]);
console.log(sheet);
