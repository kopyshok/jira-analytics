const CYR_MAP: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e',
  ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm',
  н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u',
  ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch',
  ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
};

export function slugifyCode(text: string): string {
  const lowered = text.trim().toLowerCase();
  let result = '';
  for (const ch of lowered) {
    if (ch in CYR_MAP) {
      result += CYR_MAP[ch];
    } else {
      result += ch;
    }
  }
  return result
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
}
