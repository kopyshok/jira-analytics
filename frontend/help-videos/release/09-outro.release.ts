// Финал сводного ролика: «А также» — улучшения без своей главы, число исправлений
// из заметок «Что нового» и куда смотреть подробности.
import { test } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';
import { Director } from '../director.ts';
import { MORE } from './chapters.ts';
import { RELEASE, saveClip, releaseFrame } from './common.ts';
import { outroHtml } from './slides.ts';

releaseFrame();

test('09-outro', async ({ page }) => {
  // До выпуска заметки лежат в черновиках, после — в файле версии.
  const notesDir = new URL('../../../release_notes/', import.meta.url);
  const released = new URL(`v${RELEASE}.0.json`, notesDir);
  const { notes } = JSON.parse(
    readFileSync(existsSync(released) ? released : new URL('drafts.json', notesDir), 'utf-8'),
  ) as { notes: { type: string }[] };
  const fixes = notes.filter((n) => n.type === 'fix').length;

  const d = new Director(page);
  await d.install();
  await page.setContent(outroHtml(RELEASE, MORE, fixes));
  await d.pause(900 + MORE.length * 450 + 300 + 4500);
  await saveClip(page, '09-outro');
});
