/** Ссылка на задачу в Jira: `<адрес>/browse/<ключ>`. Нет адреса или ключа — `null`. */
export function jiraBrowseUrl(
  baseUrl: string | null | undefined,
  issueKey: string | null | undefined,
): string | null {
  const base = (baseUrl ?? '').trim().replace(/\/+$/, '');
  if (!base || !issueKey) return null;
  return `${base}/browse/${issueKey}`;
}
