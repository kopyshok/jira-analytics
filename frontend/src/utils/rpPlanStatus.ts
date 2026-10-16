/** Метка и цвет статуса плана ресурсов — одинаковы для всех раскладок страницы. */
export function planStatusTag(status: string): { label: string; color: string } {
  const label = status === 'ready' ? 'Готово'
    : status === 'stale' ? 'Требуется пересчёт'
    : status === 'computing' ? 'Считается…'
    : 'Черновик';
  const color = status === 'ready' ? 'cyan'
    : status === 'stale' ? 'orange'
    : status === 'computing' ? 'blue'
    : 'default';
  return { label, color };
}
