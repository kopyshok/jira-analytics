/**
 * Копирование текста в буфер обмена.
 *
 * navigator.clipboard доступен только в secure context (HTTPS/localhost);
 * на проде по HTTP его нет — fallback на execCommand через временный textarea.
 * Возвращает true при успехе, false если оба способа не сработали.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // secure context есть, но запись отклонена — пробуем fallback ниже
  }
  try {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
