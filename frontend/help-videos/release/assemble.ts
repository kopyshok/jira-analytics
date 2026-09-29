// Склейка глав сводного ролика: data/release-video/clips/*.webm по порядку имён →
// data/release-video/release-<версия>.mp4 и сетка кадров для просмотра.
// `node --no-warnings help-videos/release/assemble.ts`. Нужен ffmpeg в PATH.
import { execFileSync } from 'node:child_process';
import { readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { CLIPS_DIR, RELEASE } from './common.ts';

const outDir = resolve(CLIPS_DIR, '..');
const clips = readdirSync(CLIPS_DIR).filter((f) => f.endsWith('.webm')).sort();
if (!clips.length) throw new Error(`Нет глав в ${CLIPS_DIR}`);

// Запись Playwright — с плавающей частотой кадров: приводим к 25 к/с перед склейкой.
// Главы по приложению начинаются с полусекунды «Загрузка…» до заголовка — её срезаем;
// заставка и финал (00, 09) — свои страницы, их не трогаем.
const inputs = clips.flatMap((f) => ['-i', resolve(CLIPS_DIR, f)]);
const trim = (f: string) => (/^0[1-8]-/.test(f) ? 'trim=start=0.5,setpts=PTS-STARTPTS,' : '');
const norm = clips.map((f, i) => `[${i}:v]${trim(f)}fps=25,scale=1920:1080,setsar=1[v${i}]`).join(';');
const concat = `${clips.map((_, i) => `[v${i}]`).join('')}concat=n=${clips.length}:v=1:a=0[out]`;
const out = resolve(outDir, `release-${RELEASE}.mp4`);
execFileSync('ffmpeg', [
  '-y', '-loglevel', 'error', ...inputs,
  '-filter_complex', `${norm};${concat}`, '-map', '[out]',
  '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '22', '-movflags', '+faststart', out,
]);
console.log(`${clips.length} глав → ${out}`);

// ponytail: кадр каждые 5 с, 6 в ряд — до 3,5 мин ролика на листе
const sheet = resolve(outDir, `release-${RELEASE}-sheet.png`);
execFileSync('ffmpeg', [
  '-y', '-loglevel', 'error', '-i', out,
  '-vf', 'fps=1/5,scale=480:-1,tile=6x7:padding=4:color=white', '-frames:v', '1', sheet,
]);
console.log(sheet);
