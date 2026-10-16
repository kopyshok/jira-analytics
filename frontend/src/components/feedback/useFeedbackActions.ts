import { useState, useSyncExternalStore } from 'react';
import { App } from 'antd';
import {
  buildContext,
  clearErrors,
  getErrorCount,
  subscribe,
  type FeedbackContext,
} from '../../utils/errorStore';
import { feedbackApi } from '../../api/feedback';
import { copyText } from '../../utils/clipboard';

function buildQuickMarkdown(ctx: FeedbackContext): string {
  const lines: string[] = [
    '# Быстрый баг-репорт',
    '',
    `**URL:** ${window.location.href}`,
    `**Время:** ${new Date().toISOString()}`,
    `**Браузер:** ${ctx.user_agent}`,
    `**Экран:** ${ctx.screen_w}×${ctx.screen_h}`,
  ];
  if (ctx.active_team) lines.push(`**Команда:** ${ctx.active_team}`);
  if (ctx.active_period) lines.push(`**Период:** ${ctx.active_period}`);
  if (ctx.theme) lines.push(`**Тема:** ${ctx.theme}`);
  lines.push('');
  lines.push(`## Консольные ошибки (${ctx.console_errors.length})`);
  if (ctx.console_errors.length === 0) {
    lines.push('— нет');
  } else {
    ctx.console_errors.forEach((e, i) => {
      lines.push(`${i + 1}. \`${e.message}\`${e.stack ? `\n   ${e.stack.split('\n')[0]}` : ''}`);
    });
  }
  lines.push('');
  lines.push(`## Сетевые ошибки (${ctx.network_errors.length})`);
  if (ctx.network_errors.length === 0) {
    lines.push('— нет');
  } else {
    ctx.network_errors.forEach((e, i) => {
      lines.push(`${i + 1}. \`${e.method} ${e.url}\` → ${e.status ?? 'network'} ${e.detail}`);
    });
  }
  return lines.join('\n');
}

/**
 * Действия обратной связи — форма и «быстрый баг». Общие для плавающей кнопки
 * и текстовой строки внизу паспорта экрана в обложке «Швейцарская».
 */
export function useFeedbackActions() {
  const { notification } = App.useApp();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const count = useSyncExternalStore(subscribe, getErrorCount);

  const handleQuickBug = async (): Promise<void> => {
    if (busy) return;
    setBusy(true);
    try {
      const ctx = buildContext();
      const md = buildQuickMarkdown(ctx);
      const copied = await copyText(md);
      await feedbackApi.createBug({
        title: 'Быстрый баг-репорт',
        body: '— быстрый репорт без описания, см. контекст',
        page_url: window.location.pathname + window.location.search,
        context: ctx as unknown as Record<string, unknown>,
      });
      clearErrors();
      notification.success({
        title: 'Баг отправлен',
        description: copied ? 'Скопирован в буфер и ушёл админу' : 'Ушёл админу',
      });
    } catch (e) {
      notification.error({
        title: 'Не удалось отправить',
        description: e instanceof Error ? e.message : 'Неизвестная ошибка',
      });
    } finally {
      setBusy(false);
    }
  };

  return { open, setOpen, busy, count, handleQuickBug };
}
