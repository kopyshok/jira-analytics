// Озвучка роликов: текст подписи → голос Яндекс SpeechKit (кэш в data/voice/cache/),
// затем голос и тихая фоновая музыка сводятся в звуковую дорожку ролика.
// Включается VOICE=1; ключ — YANDEX_SPEECHKIT_API_KEY в окружении или в .env корня проекта.
// Нужен ffmpeg в PATH.
// Музыка по умолчанию — «Ambient Corporate Background Soft» (Top-Flow), Pixabay Content License:
// коммерческое использование без указания автора.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parseEnv } from 'node:util';

export const VOICE_ON = process.env.VOICE === '1';

const ROOT = fileURLToPath(new URL('../../', import.meta.url));
export const VOICE_DIR = `${ROOT}data/voice/`;
const MUSIC = process.env.VOICE_MUSIC ?? fileURLToPath(new URL('./voice/music.mp3', import.meta.url));

/** Голос диктора (список голосов и амплуа — в документации SpeechKit, API v3). */
export const VOICE = { voice: 'lera', role: 'friendly', speed: 1.0 };
export type Voice = typeof VOICE;

/** Как читать то, что синтезатор произносит неверно. «+» перед гласной — ударение. */
const SAY: [RegExp, string][] = [
  [/Ресурс\. планир\./g, 'Ресурсное планирование'],
];

/** Громкость музыки без голоса (LUFS); под голосом она приглушается ещё сильнее. */
const MUSIC_LUFS = -32;

export type Line = { file: string; ms: number };
export type Cue = { file: string; at: number };

/** Озвучить фразу (или взять из кэша) и вернуть файл и длительность. */
export async function speak(text: string, voice: Voice = VOICE): Promise<Line> {
  const say = SAY.reduce((t, [re, to]) => t.replace(re, to), text);
  const hash = createHash('sha1').update(JSON.stringify([say, voice])).digest('hex');
  const file = `${VOICE_DIR}cache/${hash}.wav`;
  if (!existsSync(file)) {
    const res = await fetch('https://tts.api.cloud.yandex.net/tts/v3/utteranceSynthesis', {
      method: 'POST',
      headers: { Authorization: `Api-Key ${apiKey()}` },
      body: JSON.stringify({
        text: say,
        hints: [{ voice: voice.voice }, { role: voice.role }, { speed: voice.speed }],
        loudnessNormalizationType: 'LUFS',
      }),
    });
    const body = await res.text();
    // Ответ — поток JSON-объектов, в каждом кусок звука в base64.
    const chunks = [...body.matchAll(/"data"\s*:\s*"([^"]+)"/g)].map((m) => Buffer.from(m[1], 'base64'));
    if (!res.ok || !chunks.length) throw new Error(`Озвучка «${say}»: ${res.status} ${body.slice(0, 300)}`);
    mkdirSync(`${VOICE_DIR}cache`, { recursive: true });
    writeFileSync(file, Buffer.concat(chunks));
  }
  return { file, ms: Math.round(duration(file) * 1000) };
}

/**
 * Свести голос (фразы с моментами начала, мс) и музыку в дорожку ролика `video` → `out`.
 * Видео копируется как есть; музыка плавно входит и уходит и притихает, пока говорит диктор.
 */
export function mix(video: string, cues: Cue[], out: string): void {
  const dur = duration(video);
  const filter = [
    ...cues.map((c, i) => `[${i + 2}:a]aresample=48000,aformat=channel_layouts=stereo,adelay=${c.at}:all=1[v${i}]`),
    `${cues.map((_, i) => `[v${i}]`).join('')}amix=inputs=${cues.length}:normalize=0,` +
      `apad=whole_dur=${dur},atrim=duration=${dur},asplit[voice][key]`,
    `[1:a]loudnorm=I=${MUSIC_LUFS},aresample=48000,atrim=duration=${dur},` +
      `afade=t=in:d=1.5,afade=t=out:st=${Math.max(0, dur - 2.5)}:d=2.5[bed]`,
    '[bed][key]sidechaincompress=threshold=0.02:ratio=4:attack=40:release=600[ducked]',
    '[voice][ducked]amix=inputs=2:normalize=0:duration=first[a]',
  ].join(';');
  execFileSync('ffmpeg', [
    '-y', '-loglevel', 'error', '-i', video, '-stream_loop', '-1', '-i', MUSIC,
    ...cues.flatMap((c) => ['-i', c.file]),
    '-filter_complex', filter, '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'libopus', '-b:a', '64k', out,
  ]);
}

function duration(file: string): number {
  return Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]));
}

function apiKey(): string {
  const env = `${ROOT}.env`;
  const key = process.env.YANDEX_SPEECHKIT_API_KEY
    ?? (existsSync(env) ? parseEnv(readFileSync(env, 'utf8')).YANDEX_SPEECHKIT_API_KEY : undefined);
  if (!key) throw new Error('Нет ключа озвучки: добавьте YANDEX_SPEECHKIT_API_KEY в .env');
  return key;
}
