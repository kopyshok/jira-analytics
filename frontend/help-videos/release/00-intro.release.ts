// Заставка сводного ролика: «Что нового в версии …» и оглавление глав.
import { test } from '@playwright/test';
import { Director } from '../director.ts';
import { CHAPTERS } from './chapters.ts';
import { RELEASE, saveClip, releaseFrame } from './common.ts';
import { introHtml } from './slides.ts';

releaseFrame();

test('00-intro', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await page.setContent(introHtml(RELEASE, CHAPTERS));
  await d.say(`Что нового в версии ${RELEASE}. Коротко о главном — по ходу планирования квартала.`);
  // Последний пункт появляется через 1300 + 7×380 мс; дальше — время прочитать список.
  await d.pause(1300 + (CHAPTERS.length - 1) * 380 + 3800);
  await saveClip(d, '00-intro');
});
