/** Имя файла из заголовка Content-Disposition: `filename*` (UTF-8) приоритетнее `filename`. */
export function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const star = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(header);
  if (star) {
    try {
      const name = decodeURIComponent(star[2].trim());
      if (name) return name;
    } catch {
      // битая кодировка — пробуем обычное имя
    }
  }
  const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(header);
  const name = (plain?.[1] ?? plain?.[2] ?? '').trim();
  return name || null;
}
